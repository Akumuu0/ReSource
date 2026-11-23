"""Tests for the AI features. They never call the real AI provider:
either there is no key (fallback) or AIGateway.call_model is replaced by a fake."""
import json
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.common import BusinessRuleError
from accounts.models import Notification
from accounts.sample_data import build_sample_world
from assets.models import Asset, Category
from assets.services import AssetService
from resource_requests.models import Request
from resource_requests.services import RequestService
from sustainability.models import AIReport
from sustainability.services import SummaryService

from .classification import ClassificationService
from .gateway import AIGateway
from .models import AIOutput, Recommendation
from .ranking import WEIGHTS, RankingModel
from .report_generator import ReportGenerator

NEXT_MONTH = date.today() + timedelta(days=30)


def fake_ai(data):
    """Pretend the AI answered with `data`."""
    return patch.object(AIGateway, "call_model", return_value=(data, "OK"))


@override_settings(GEMINI_API_KEY="")
class GatewayTests(TestCase):
    def setUp(self):
        self.w = build_sample_world()
        self.w.physics_rep.first_name, self.w.physics_rep.last_name = "Sara", "Khalid"
        self.w.physics_rep.save()

    def test_personal_data_is_removed_before_sending(self):
        text = "Ask Sara Khalid (sara@uni.ac.ae, ID 100064869) or physics.rep about R-2026-0391"
        clean = AIGateway.strip_personal_data(text)
        for secret in ["Sara", "Khalid", "sara@uni.ac.ae", "100064869", "physics.rep", "R-2026-0391"]:
            self.assertNotIn(secret, clean)

    def test_without_a_key_the_fallback_is_used_and_recorded(self):
        result = AIGateway().run(AIOutput.CLASSIFICATION, "system", "prompt", {}, fallback=lambda: {"x": 1},
                                 user=self.w.eng_coord)
        self.assertFalse(result.used_ai)
        self.assertEqual(result.data, {"x": 1})
        self.assertEqual(result.output.source, "AI unavailable, rule-based result")
        self.assertEqual(result.output.note, "No API key set")

    def test_a_good_ai_answer_is_used_and_recorded(self):
        with fake_ai({"x": 2, "confidence": 0.9}):
            result = AIGateway().run(AIOutput.CLASSIFICATION, "system", "prompt", {}, fallback=lambda: {"x": 1},
                                     user=self.w.eng_coord)
        self.assertTrue(result.used_ai)
        self.assertEqual((result.output.confidence, result.output.confidence_level), (0.9, "High"))

    def test_an_answer_that_fails_validation_falls_back(self):
        with fake_ai({"x": 2}):
            result = AIGateway().run(AIOutput.CLASSIFICATION, "s", "p", {}, fallback=lambda: {"x": 1},
                                     user=self.w.eng_coord, validate=lambda data: "bad answer")
        self.assertEqual(result.data, {"x": 1})
        self.assertIn("bad answer", result.output.note)


@override_settings(GEMINI_API_KEY="")
class ClassificationTests(TestCase):
    def setUp(self):
        self.w = build_sample_world()
        Category.objects.create(name="Computers & Monitors", keywords="monitor,laptop,desktop,dell")
        Category.objects.create(name="Audio-Visual", keywords="projector,speaker")
        self.form = {"name": "Dell 24-inch monitor", "description": "small scratch", "quantity": "3",
                     "estimated_value": "650", "weight_kg": "4.5", "tags": ""}

    def test_rule_based_fallback_gives_a_confidence_per_field(self):
        data = ClassificationService().suggest(self.w.eng_coord, "Dell 24-inch monitor", "small scratch").data
        self.assertEqual((data["category"], data["condition"]), ("Computers & Monitors", "Good"))
        # 2 keywords found -> 0.3 + 2 x 0.15; no condition word -> 0.3; keywords among the tags -> 0.5
        self.assertEqual((data["category_confidence"], data["condition_confidence"], data["tags_confidence"]),
                         (0.6, 0.3, 0.5))
        self.assertEqual(data["confidence"], 0.3)  # overall = the lowest
        data = ClassificationService().suggest(self.w.eng_coord, "Projector", "broken lamp").data
        self.assertEqual((data["category"], data["condition"]), ("Audio-Visual", "Poor"))

    def test_ai_category_must_be_on_the_approved_list(self):
        with fake_ai({"category": "Spaceships", "condition": "Good", "tags": [], "confidence": 0.9, "reason": "?"}):
            result = ClassificationService().suggest(self.w.eng_coord, "Dell monitor", "")
        self.assertFalse(result.used_ai)
        self.assertEqual(result.data["category"], "Computers & Monitors")

    def test_suggestion_saves_nothing_and_the_decision_is_recorded_on_save(self):
        self.client.force_login(self.w.eng_coord)
        assets_before = Asset.objects.count()
        response = self.client.post(reverse("asset_create"), dict(self.form, action="suggest"))
        self.assertContains(response, "AI unavailable, rule-based result")
        self.assertEqual(Asset.objects.count(), assets_before)  # nothing saved automatically

        output = AIOutput.objects.get(feature=AIOutput.CLASSIFICATION)
        computers = Category.objects.get(name="Computers & Monitors")
        self.client.post(reverse("asset_create"), dict(self.form, action="save", ai_output_id=output.pk,
                                                       category=computers.pk, condition="Fair"))
        output.refresh_from_db()
        self.assertEqual(Asset.objects.count(), assets_before + 1)
        self.assertEqual(output.human_decision, "Category accepted; condition edited (Good -> Fair); tags edited")
        self.assertEqual(output.decided_by, self.w.eng_coord)

    def test_each_field_is_accepted_or_rejected_on_its_own(self):
        self.client.force_login(self.w.eng_coord)
        self.client.post(reverse("asset_create"), dict(self.form, action="suggest"))
        output = AIOutput.objects.get(feature=AIOutput.CLASSIFICATION)
        computers = Category.objects.get(name="Computers & Monitors")

        response = self.client.post(reverse("asset_create"), dict(self.form, action="accept:category", ai_output_id=output.pk))
        self.assertEqual(response.context["form"].initial["category"], computers.pk)  # only this field filled in
        self.assertEqual(response.context["accepted"], "category")

        response = self.client.post(reverse("asset_create"), dict(self.form, action="reject:tags", ai_output_id=output.pk,
                                                                  accepted="category"))
        self.assertEqual((response.context["accepted"], response.context["rejected"]), ("category", "tags"))
        self.assertEqual(Asset.objects.filter(name="Dell 24-inch monitor").count(), 0)  # still nothing saved

        self.client.post(reverse("asset_create"), dict(self.form, action="save", ai_output_id=output.pk,
                                                       accepted="category", rejected="tags",
                                                       category=computers.pk, condition="Good"))
        output.refresh_from_db()
        self.assertEqual(output.human_decision, "Category accepted; condition accepted; tags rejected")


@override_settings(GEMINI_API_KEY="")
class RankingTests(TestCase):
    def setUp(self):
        self.w = build_sample_world()
        self.need = RequestService.submit_need(self.w.physics_rep, self.w.lab, 2,
                                               "Two oscilloscopes for a teaching lab", NEXT_MONTH)

    def add_analog_scope(self):
        """The second candidate of the design example: 50 MHz, Fair, 1 unit, owned by Engineering."""
        analog = AssetService.register(self.w.eng_coord, {
            "name": "Analog oscilloscope", "description": "50 MHz dual-trace analog oscilloscope",
            "category": self.w.lab, "condition": "Fair", "tags": "", "quantity": 1,
            "estimated_value": Decimal("3000"), "weight_kg": Decimal("3.0"), "repair_cost": Decimal("150"),
        })
        AssetService.publish(self.w.eng_coord, analog)
        return analog

    def test_weights_add_up_to_one_and_a_perfect_match_scores_100(self):
        self.assertAlmostEqual(sum(WEIGHTS.values()), 1.0)
        self.assertEqual(RankingModel.score({name: 1.0 for name in WEIGHTS}), 100)

    def test_confidence_follows_the_design_worked_example(self):
        # Design Section 17.4: score 92 -> 0.84 (High), score 62 -> 0.57 (Medium)
        self.assertEqual(RankingModel.confidence(92), 0.84)
        self.assertEqual(RankingModel.confidence(62), 0.57)

    def test_the_oscilloscope_ranks_first_with_an_explainable_score(self):
        recommendations, output = RankingModel().rank(self.w.physics_rep, self.need)
        best = recommendations[0]
        self.assertEqual(best.asset, self.w.scope)
        # function 1/2 ("oscilloscope" yes, "teaching" no), Good 0.9, other campus 0.55,
        # moving 1 - 120 / (0.15 x 4,200) = 0.81, the only candidate so the most carbon saved
        self.assertEqual(json.loads(best.factors), {
            "function": 0.5, "quantity": 1.0, "condition": 0.9, "location": 0.55,
            "ready": 1.0, "repair": 1.0, "transfer": 0.81, "carbon": 1.0})
        expected = round(100 * (0.35 * 0.5 + 0.15 + 0.10 * 0.9 + 0.10 * 0.55 + 0.10 + 0.08 + 0.07 * 0.81 + 0.05))
        self.assertEqual(best.score, expected)
        self.assertEqual(best.confidence, RankingModel.confidence(expected))
        self.assertEqual(best.limitation, "matches only part of your description")  # largest gap: 0.35 x 0.5
        self.assertTrue(best.reason)
        self.assertEqual(output.source, "AI unavailable, rule-based result")
        self.assertEqual(output.confidence, best.confidence)

    def test_specifications_and_minimum_condition_lower_a_candidate(self):
        analog = self.add_analog_scope()
        self.need.specifications, self.need.min_condition = "At least 70 MHz", "Good"
        self.assertEqual(RankingModel.unmet_specs(self.need, analog), ["70 MHz"])
        self.assertEqual(RankingModel.unmet_specs(self.need, self.w.scope), [])
        factors = RankingModel.factors(self.need, analog, largest_carbon=RankingModel.carbon(self.need, self.w.scope))
        # 2 of 3 words ("oscilloscope" and "MHz" yes, "teaching" no), halved for the unmet 70 MHz
        self.assertEqual(factors["function"], 0.33)
        self.assertEqual(factors["condition"], 0.3)   # Fair is below the Good minimum
        self.assertEqual(factors["location"], 0.55)   # Engineering is on another campus
        self.assertEqual(factors["repair"], 0.95)     # 1 - 150 / 3,000

    def test_own_department_assets_are_not_candidates(self):
        need = RequestService.submit_need(self.w.eng_rep, self.w.lab, 1, "Oscilloscope", NEXT_MONTH)
        self.assertEqual(RankingModel.candidates(need), [])  # the only oscilloscope is Engineering's own
        with self.assertRaisesMessage(BusinessRuleError, "This asset already belongs to your department"):
            RequestService.choose_match(self.w.eng_rep, need, self.w.scope)

    def test_a_recommendation_only_answers_its_own_request(self):
        other = RequestService.submit_need(self.w.physics_rep, self.w.lab, 2, "Oscilloscopes", NEXT_MONTH)
        self.client.force_login(self.w.physics_rep)
        self.client.get(reverse("request_matches", args=[self.need.pk]))
        rec = Recommendation.objects.get(rank=1)
        self.assertEqual(rec.request, self.need)
        response = self.client.post(reverse("request_choose_match", args=[other.pk, rec.pk]), follow=True)
        self.assertContains(response, "This recommendation was made for another request")
        other.refresh_from_db()
        self.assertEqual((other.state, other.asset), (Request.OPEN, None))

    def test_badge_says_rule_based_unless_the_ai_answered(self):
        self.client.force_login(self.w.physics_rep)
        page = self.client.get(reverse("request_matches", args=[self.need.pk]))
        self.assertContains(page, "Rule-based")
        self.assertNotContains(page, "AI-ranked")
        with fake_ai({"reasons": ["Same function, enough units."]}):
            page = self.client.get(reverse("request_matches", args=[self.need.pk]))
        self.assertContains(page, "AI-ranked")

    def test_high_urgency_doubles_the_ready_weight(self):
        self.need.urgency = "High"
        weights = RankingModel.weights_for(self.need)
        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertAlmostEqual(weights["ready"], 0.20 / 1.10)

    def test_ai_only_writes_the_reasons(self):
        with fake_ai({"reasons": ["Same function, enough units."]}):
            recommendations, output = RankingModel().rank(self.w.physics_rep, self.need)
        self.assertTrue(output.used_ai)
        self.assertEqual(recommendations[0].reason, "Same function, enough units.")
        self.assertNotIn("A-2026-0412", output.input_text)  # no record codes are sent
        self.assertNotIn("Engineering", output.input_text)  # no department names either

    def test_choosing_a_match_sends_the_request_to_the_owner(self):
        RequestService.choose_match(self.w.physics_rep, self.need, self.w.scope)
        self.need.refresh_from_db()
        self.assertEqual((self.need.state, self.need.asset), (Request.SUBMITTED, self.w.scope))
        self.assertTrue(Notification.objects.filter(recipient=self.w.eng_coord, event_type="Request made").exists())

    def test_selecting_the_top_match_needs_no_reason(self):
        self.client.force_login(self.w.physics_rep)
        self.client.get(reverse("request_matches", args=[self.need.pk]))
        top = Recommendation.objects.get(rank=1)
        self.client.post(reverse("request_choose_match", args=[self.need.pk, top.pk]))
        self.need.refresh_from_db()
        top.output.refresh_from_db()
        self.assertEqual((self.need.state, self.need.recommendation), (Request.SUBMITTED, top))
        self.assertEqual(top.output.human_decision, "Selected the top match: A-2026-0412")

    def test_choosing_another_match_needs_a_reason_and_approvers_see_it(self):
        analog = self.add_analog_scope()
        self.client.force_login(self.w.physics_rep)
        self.client.get(reverse("request_matches", args=[self.need.pk]))
        second = Recommendation.objects.get(rank=2)
        self.assertEqual(second.asset, analog)

        self.client.post(reverse("request_choose_match", args=[self.need.pk, second.pk]), {"reason": "  "})
        self.need.refresh_from_db()
        self.assertEqual(self.need.state, Request.OPEN)  # refused: no reason

        self.need.quantity = 1  # the analog scope has 1 unit
        self.need.save()
        self.client.post(reverse("request_choose_match", args=[self.need.pk, second.pk]), {"reason": "Same building"})
        self.need.refresh_from_db()
        self.assertEqual((self.need.state, self.need.recommendation), (Request.SUBMITTED, second))
        second.output.refresh_from_db()
        self.assertTrue(second.output.human_decision.startswith("Chose match 2"))

        self.client.force_login(self.w.admin)
        response = self.client.get(reverse("request_detail", args=[self.need.pk]))
        self.assertContains(response, "How this asset was chosen")
        self.assertContains(response, "ranked 2 of 2")
        self.assertContains(response, "Same building")
        self.assertContains(response, "Request made by physics.rep")  # the History card

    def test_check_listings_ranks_without_saving_the_need(self):
        self.client.force_login(self.w.physics_rep)
        requests_before = Request.objects.count()
        response = self.client.post(reverse("need_create"), {
            "action": "check", "category": self.w.lab.pk, "purpose": "Oscilloscopes for a lab", "quantity": 2,
            "needed_by": NEXT_MONTH.isoformat(), "urgency": "Medium", "min_condition": "", "specifications": ""})
        self.assertEqual(response.context["listings"][0].asset, self.w.scope)
        self.assertEqual(Request.objects.count(), requests_before)
        self.assertIsNone(response.context["listings"][0].request)  # the need is not saved, so no request

    def test_rejecting_all_matches_closes_the_need_with_the_reason(self):
        self.client.force_login(self.w.physics_rep)
        self.client.get(reverse("request_matches", args=[self.need.pk]))
        output = AIOutput.objects.get(feature=AIOutput.MATCHING)
        self.client.post(reverse("request_reject_matches", args=[self.need.pk]),
                         {"reason": "Need 200 MHz", "ai_output_id": output.pk})
        self.need.refresh_from_db()
        output.refresh_from_db()
        self.assertEqual(self.need.state, Request.CANCELLED)
        self.assertIn("Need 200 MHz", self.need.reason)
        self.assertEqual(output.human_decision, "Rejected all matches: Need 200 MHz")


@override_settings(GEMINI_API_KEY="")
class ReportGeneratorTests(TestCase):
    def setUp(self):
        self.w = build_sample_world()
        self.today = date.today()

    def test_check_marks_go_on_the_figures_not_the_dates(self):
        report = ReportGenerator().generate(self.w.admin, self.today.replace(day=1), self.today)
        pieces = ReportGenerator.mark_numbers(report.draft_text, report)
        numbers = [piece for piece in pieces if piece["number"]]
        self.assertEqual([piece["text"] for piece in numbers], ["0", "0", "0.0", "0.0"])  # the four figures
        self.assertTrue(all(piece["checked"] for piece in numbers))
        self.assertEqual("".join(piece["text"] for piece in pieces), report.draft_text)  # nothing lost

    def test_number_check(self):
        allowed = {38, 41200}
        self.assertEqual(ReportGenerator.check_numbers("38 items reused, AED 41,200 not spent, less CO2e.", allowed), "")
        self.assertIn("39", ReportGenerator.check_numbers("39 items reused.", allowed))

    def test_without_a_key_the_template_text_is_used_and_figures_are_frozen(self):
        report = ReportGenerator().generate(self.w.admin, self.today, self.today)
        self.assertIn("0 items were reused", report.draft_text)
        self.assertFalse(report.ai_output.used_ai)
        self.assertEqual(report.figures.count(), 4)

    def test_an_ai_summary_with_an_invented_number_is_replaced(self):
        with fake_ai({"summary": "We reused 0 items and saved AED 99."}):
            report = ReportGenerator().generate(self.w.admin, self.today, self.today)
        self.assertFalse(report.ai_output.used_ai)
        self.assertIn("the number 99", report.ai_output.note)
        self.assertNotIn("99", report.draft_text)

    def test_an_ai_summary_with_correct_numbers_is_kept(self):
        with fake_ai({"summary": "We reused 0 items, so AED 0 was saved and 0.0 kg diverted (0.0 kg CO2e)."}):
            report = ReportGenerator().generate(self.w.admin, self.today, self.today)
        self.assertTrue(report.ai_output.used_ai)

    def test_administrator_edits_then_publishes(self):
        report = ReportGenerator().generate(self.w.admin, self.today, self.today)
        SummaryService.publish(self.w.admin, report, report.draft_text + " Well done, everyone.")
        report.refresh_from_db()
        self.assertEqual(report.state, AIReport.PUBLISHED)
        self.assertEqual(report.ai_output.human_decision, "Published after edits")

    def test_only_administrators_generate_and_publish(self):
        with self.assertRaises(PermissionDenied):
            ReportGenerator().generate(self.w.eng_coord, self.today, self.today)
        report = ReportGenerator().generate(self.w.admin, self.today, self.today)
        with self.assertRaises(PermissionDenied):
            SummaryService.publish(self.w.eng_coord, report, "text")
        self.client.force_login(self.w.physics_rep)
        self.assertEqual(self.client.get(reverse("summary_detail", args=[report.pk])).status_code, 403)
