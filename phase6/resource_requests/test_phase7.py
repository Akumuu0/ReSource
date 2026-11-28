"""Phase 7 tests of decline reasons, dashboard figures and approvals (Rashid Alzaabi).

BB-R1 to BB-R5 are black-box tests: the classes of the decline reason and of the dashboard figures
(Table 6-5 of the test document). WB-R1 to WB-R5 are white-box tests: the paths and loop cases of
ApprovalService.check_not_involved and every branch of Request.is_visible_to (Table 7-7).
BB-R6 checks the period of an AI summary: start before, on or after the end date (Table 6-5).
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.common import BusinessRuleError
from accounts.models import User
from accounts.sample_data import build_sample_world
from sustainability.forms import SummaryForm
from sustainability.models import AIReport
from sustainability.services import SustainabilityCalculator

from .models import Request
from .services import ApprovalService, RequestService

NEXT_MONTH = date.today() + timedelta(days=30)


class DeclineReasonBlackBoxTests(TestCase):
    """Valid: at least one character that is not a space. Invalid: empty, spaces only, missing."""

    def setUp(self):
        self.w = build_sample_world()
        self.req = RequestService.submit(self.w.physics_rep, self.w.scope, 1, "Teaching lab", NEXT_MONTH)

    def decline(self, reason):
        ApprovalService.decline(self.w.eng_coord, self.req, reason)

    def test_bb_r1_empty_reason_is_refused(self):
        with self.assertRaisesMessage(BusinessRuleError, "A reason is required."):
            self.decline("")

    def test_bb_r2_spaces_only_reason_is_refused(self):
        with self.assertRaisesMessage(BusinessRuleError, "A reason is required."):
            self.decline(" ")

    def test_bb_r3_missing_reason_is_refused(self):
        with self.assertRaisesMessage(BusinessRuleError, "A reason is required."):
            self.decline(None)  # the field was not sent

    def test_bb_r4_one_character_reason_is_accepted(self):
        self.decline("x")
        self.req.refresh_from_db()
        self.assertEqual((self.req.state, self.req.reason), (Request.REJECTED, "x"))


class DashboardFigureBlackBoxTests(TestCase):
    """The figures as people read them: zero, small values, and values with thousands."""

    def test_bb_r5_zero_small_and_large_values(self):
        cases = [
            ((0, "0", "0", "0"), ["0", "0", "0.0", "0.0"]),
            ((2, "8400", "5.2", "119.184"), ["2", "8,400", "5.2", "119.2"]),
            ((38, "41200", "1234.56", "28296.4"), ["38", "41,200", "1,234.6", "28,296.4"]),
        ]
        for (items, cost, waste, co2e), expected in cases:
            totals = {"items_reused": items, "cost_avoided": Decimal(cost),
                      "waste_kg": Decimal(waste), "co2e_kg": Decimal(co2e)}
            shown = SustainabilityCalculator.display(totals)
            with self.subTest(totals=totals):
                self.assertEqual([shown["items_reused"], shown["cost_avoided"], shown["waste_kg"], shown["co2e_kg"]],
                                 expected)


class ApprovalIndependenceWhiteBoxTests(TestCase):
    """check_not_involved: one decision on the requester, then a loop over the saved approvals."""

    def setUp(self):
        self.w = build_sample_world()
        self.req = RequestService.submit(self.w.physics_rep, self.w.scope, 1, "Teaching lab", NEXT_MONTH)

    def test_wb_r1_requester_path(self):
        with self.assertRaisesMessage(BusinessRuleError, "You submitted this request"):
            ApprovalService.check_not_involved(self.w.physics_rep, self.req)

    def test_wb_r2_loop_zero_times_no_approvals_yet(self):
        self.assertEqual(self.req.approvals.count(), 0)
        self.assertIsNone(ApprovalService.check_not_involved(self.w.admin, self.req))

    def test_wb_r3_loop_once_releaser_found(self):
        ApprovalService.release(self.w.eng_coord, self.req)
        self.w.eng_coord.role = User.ADMINISTRATOR  # a change of role must not get around the rule
        self.w.eng_coord.save()
        self.assertEqual(self.req.approvals.count(), 1)
        with self.assertRaisesMessage(BusinessRuleError, "You released this request"):
            ApprovalService.check_not_involved(self.w.eng_coord, self.req)

    def test_wb_r4_loop_once_other_person_passes(self):
        ApprovalService.release(self.w.eng_coord, self.req)
        self.assertEqual(self.req.approvals.count(), 1)
        self.assertIsNone(ApprovalService.check_not_involved(self.w.admin, self.req))


class VisibilityWhiteBoxTests(TestCase):
    """Request.is_visible_to: Administrator, requesting department, owning department, another department."""

    def setUp(self):
        self.w = build_sample_world()

    def test_wb_r5_every_branch(self):
        req = RequestService.submit(self.w.physics_rep, self.w.scope, 1, "Teaching lab", NEXT_MONTH)
        self.assertTrue(req.is_visible_to(self.w.admin))  # B1: Administrator
        self.assertTrue(req.is_visible_to(self.w.physics_coord))  # B2: requesting department (Physics)
        self.assertTrue(req.is_visible_to(self.w.eng_rep))  # B3: owning department (Engineering)
        self.assertFalse(req.is_visible_to(self.w.fac_rep))  # B4: another department
        need = RequestService.submit_need(self.w.physics_rep, self.w.lab, 2, "Two oscilloscopes", NEXT_MONTH)
        self.assertFalse(need.is_visible_to(self.w.eng_rep))  # B5: open need, no owner yet


class SummaryPeriodBlackBoxTests(TestCase):
    """Valid: the start is on or before the end. Invalid: the start is after the end."""

    @override_settings(GEMINI_API_KEY="")
    def test_bb_r6_start_before_on_or_after_the_end(self):
        cases = [(date(2026, 11, 1), date(2026, 11, 27), True), (date(2026, 11, 27), date(2026, 11, 27), True),
                 (date(2026, 11, 28), date(2026, 11, 27), False)]
        for start, end, valid in cases:
            form = SummaryForm({"period_start": start, "period_end": end})
            with self.subTest(start=start, end=end):
                self.assertEqual(form.is_valid(), valid)
                if not valid:
                    self.assertEqual(form.non_field_errors(), ["The start date must be before the end date."])
        # The same reversed period on the page: an error message and no summary.
        w = build_sample_world()
        self.client.force_login(w.admin)
        response = self.client.post(reverse("summary_create"), {"period_start": "2026-11-28",
                                                                "period_end": "2026-11-27"}, follow=True)
        self.assertContains(response, "Please choose a valid period.")
        self.assertEqual(AIReport.objects.count(), 0)
