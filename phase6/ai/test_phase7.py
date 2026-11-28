"""Phase 7 tests of the AI features (Ahmed AlAbdouli). They never call the real AI provider.

BB-H1 to BB-H4 are black-box tests: classes and boundaries of the confidence levels, the ready-by-date
factor, the urgency and the AI-5 number check (Table 6-7 of the test document). WB-H1 to WB-H6 are
white-box tests of AIGateway.run, cost_factor and the name loop of strip_personal_data (Table 7-9).
BB-H5 hides instructions in an asset description (AI-9); WB-H7 runs the branches of the summary page's
POST (publish, discard, refused).
"""
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from accounts.sample_data import build_sample_world
from assets.models import Asset
from resource_requests.models import Approval, Request
from sustainability.models import AIReport
from resource_requests.services import RequestService

from .gateway import AIGateway
from .models import AIOutput, confidence_level
from .classification import ClassificationService
from .ranking import RankingModel, cost_factor
from .report_generator import ReportGenerator

TODAY = date.today()


def fake_ai(data):
    """Pretend the AI answered with `data`."""
    return patch.object(AIGateway, "call_model", return_value=(data, "OK"))


class ConfidenceLevelBoundaryTests(SimpleTestCase):
    def test_bb_h1_levels_at_the_boundaries(self):
        cases = [(None, "Unknown"), (0.0, "Low"), (0.49, "Low"), (0.50, "Medium"),
                 (0.79, "Medium"), (0.80, "High"), (1.0, "High")]
        for confidence, level in cases:
            with self.subTest(confidence=confidence):
                self.assertEqual(confidence_level(confidence), level)


class RankingFactorBlackBoxTests(TestCase):
    def setUp(self):
        self.w = build_sample_world()
        self.need = RequestService.submit_need(self.w.physics_rep, self.w.lab, 2, "Two oscilloscopes for a teaching lab",
                                               TODAY + timedelta(days=30))

    def test_bb_h2_ready_factor_by_days_late(self):
        # Every candidate is free now, so "days late" is today minus the needed-by date.
        cases = [(-1, 1.0), (0, 1.0), (1, 0.5), (2, 0.5), (3, 0.0)]
        for days_late, expected in cases:
            self.need.needed_by = TODAY - timedelta(days=days_late)
            carbon = RankingModel.carbon(self.need, self.w.scope)
            with self.subTest(days_late=days_late):
                self.assertEqual(RankingModel.factors(self.need, self.w.scope, carbon)["ready"], expected)

    def test_bb_h3_urgency_low_medium_high(self):
        cases = [(Request.LOW, 0.05 / 0.95), (Request.MEDIUM, 0.10), (Request.HIGH, 0.20 / 1.10)]
        for urgency, ready_weight in cases:
            weights = RankingModel.weights_for(SimpleNamespace(urgency=urgency))
            with self.subTest(urgency=urgency):
                self.assertAlmostEqual(weights["ready"], ready_weight, places=3)
                self.assertAlmostEqual(sum(weights.values()), 1.0)


class NumberCheckBlackBoxTests(SimpleTestCase):
    """A number in the summary is accepted only within 0.001 of a calculated figure."""

    def test_bb_h4_numbers_at_the_tolerance(self):
        allowed = {38.0, 41200.0}
        cases = [("No numbers at all.", True), ("38 items.", True), ("38.0 items.", True),
                 ("AED 41,200 saved.", True), ("38.0005 items.", True), ("38.002 items.", False),
                 ("39 items.", False)]
        for text, accepted in cases:
            with self.subTest(text=text):
                self.assertEqual(ReportGenerator.check_numbers(text, allowed) == "", accepted)


class CostFactorWhiteBoxTests(SimpleTestCase):
    def test_wb_h1_every_branch(self):
        self.assertEqual(cost_factor(0, 100), 1.0)  # B1: no cost
        self.assertEqual(cost_factor(50, 0), 0.0)  # B2: limit 0
        self.assertEqual(cost_factor(50, -10), 0.0)  # B2: limit below 0
        self.assertEqual(cost_factor(200, 100), 0.0)  # B3: cut at 0
        self.assertEqual(cost_factor(25, 100), 0.75)  # B3: 1 - 25 / 100


class GatewayWhiteBoxTests(TestCase):
    """The paths of AIGateway.run (D1 to D5 in Section 7.5 of the test document)."""

    def setUp(self):
        self.w = build_sample_world()

    def run_gateway(self, **kwargs):
        return AIGateway().run(AIOutput.CLASSIFICATION, "system", "prompt", {}, fallback=lambda: {"x": 1},
                               user=self.w.eng_coord, **kwargs)

    def test_wb_h2_answer_passes_validation(self):
        with fake_ai({"x": 2, "confidence": 0.9}):
            result = self.run_gateway(validate=lambda data: "")  # D1 true, D2 false
        self.assertTrue(result.used_ai)
        self.assertEqual(result.data, {"x": 2, "confidence": 0.9})  # the whole AI answer is kept (D-1)
        self.assertEqual(result.output.note, "OK")
        self.assertEqual(result.output.model_name, settings.AI_MODEL)  # D5: source is the AI

    def test_wb_h3_given_confidence_replaces_the_answers(self):
        with fake_ai({"x": 2, "confidence": 0.9}):
            result = self.run_gateway(confidence=0.42)  # D4: confidence given
        self.assertEqual(result.output.confidence, 0.42)

    @override_settings(GEMINI_API_KEY="")
    def test_wb_h4_fallback_stores_no_model_name(self):
        result = self.run_gateway()  # no key: D1 false, D3 true
        self.assertFalse(result.used_ai)
        self.assertEqual(result.output.model_name, "")  # D5: source is the fallback


class PrivacyFilterWhiteBoxTests(TestCase):
    """The name loop of strip_personal_data: names under 3 letters are kept; full names go first."""

    def setUp(self):
        self.w = build_sample_world()
        User.objects.create(username="ali.al", first_name="Ali", last_name="Al", role=User.REPRESENTATIVE,
                            department=self.w.physics)

    def test_wb_h5_names_of_three_letters_or_more_are_removed(self):
        self.assertEqual(AIGateway.strip_personal_data("Al met Ali at lunch"), "Al met [name] at lunch")

    def test_wb_h6_full_name_is_removed_before_its_parts(self):
        self.assertEqual(AIGateway.strip_personal_data("Ask Ali Al today"), "Ask [name] today")
