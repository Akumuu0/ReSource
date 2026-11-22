"""Tests for the AI features. They never call the real AI provider:
either there is no key (fallback) or AIGateway.call_model is replaced by a fake."""
from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.sample_data import build_sample_world
from assets.models import Asset, Category

from .classification import ClassificationService
from .gateway import AIGateway
from .models import AIOutput

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
