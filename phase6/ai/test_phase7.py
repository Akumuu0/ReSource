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
