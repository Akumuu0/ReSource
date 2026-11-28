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
