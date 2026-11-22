"""Tests for the dashboard formulas (C7) and notifications (C8)."""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.sample_data import build_sample_world
from assets.models import Category
from assets.services import AssetService
from resource_requests.services import ApprovalService, RequestService, TransferService

from .models import CategoryValue
from .services import SustainabilityCalculator

NEXT_MONTH = date.today() + timedelta(days=30)


def complete_transfer(w, quantity=2, asset=None):
    req = RequestService.submit(w.physics_rep, asset or w.scope, quantity, "Teaching lab", NEXT_MONTH)
    ApprovalService.release(w.eng_coord, req)
    ApprovalService.approve(w.admin, req)
    TransferService.hand_over(w.eng_coord, req)
    TransferService.confirm_receipt(w.physics_rep, req, "Good")
    return req


class DashboardFormulaTests(TestCase):
    def setUp(self):
        self.w = build_sample_world(units=2)

    def test_formulas_match_the_design_worked_example(self):
        # Design Section 18.3: 2 oscilloscopes, AED 4,200 and 2.6 kg each, factor 22.92.
        complete_transfer(self.w, quantity=2)
        totals, rows = SustainabilityCalculator().calculate()
        self.assertEqual(totals["items_reused"], 2)
        self.assertEqual(totals["cost_avoided"], Decimal("8400"))
        self.assertEqual(totals["waste_kg"], Decimal("5.2"))
        self.assertEqual(totals["co2e_kg"], Decimal("119.18"))  # 5.2 x 22.92 = 119.184
        self.assertEqual(SustainabilityCalculator.display(totals)["co2e_kg"], "119.2")

    def test_only_confirmed_receipts_count(self):
        req = RequestService.submit(self.w.physics_rep, self.w.scope, 2, "Lab", NEXT_MONTH)
        ApprovalService.release(self.w.eng_coord, req)
        ApprovalService.approve(self.w.admin, req)
        TransferService.hand_over(self.w.eng_coord, req)  # not received yet
        totals, rows = SustainabilityCalculator().calculate()
        self.assertEqual(totals["items_reused"], 0)

    def test_department_and_period_filters(self):
        complete_transfer(self.w)
        self.assertEqual(SustainabilityCalculator(department=self.w.physics).calculate()[0]["items_reused"], 2)
        self.assertEqual(SustainabilityCalculator(department=self.w.engineering).calculate()[0]["items_reused"], 0)
        last_year = date.today() - timedelta(days=365)
        self.assertEqual(SustainabilityCalculator(end=last_year).calculate()[0]["items_reused"], 0)

    def test_emission_factor_comes_from_category_value(self):
        # A newer version of the factor replaces the 22.92 of the sample world.
        CategoryValue.objects.create(category=self.w.lab, value_type=CategoryValue.EMISSION_FACTOR,
                                     value=Decimal("10"), unit="kg CO2e per kg", source="test",
                                     effective_date=date(2026, 1, 1), version=2)
        complete_transfer(self.w)
        self.assertEqual(SustainabilityCalculator().calculate()[0]["co2e_kg"], Decimal("52.00"))

    def test_dashboard_page_shows_each_formula_and_source(self):
        complete_transfer(self.w)
        self.client.force_login(self.w.fac_rep)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "kg diverted x the category&#x27;s emission factor")
        self.assertContains(response, "EPA WARM version 16")
        self.assertContains(response, "8,400")
        self.assertNotContains(response, "left out of CO2e")  # the oscilloscopes have a factor: no missing data

    def test_category_without_emission_factor_is_left_out_of_co2e(self):
        # FR-13.8: no factor -> not in the CO2e total, but listed under "Missing data" with a count.
        furniture = Category.objects.create(name="Furniture")  # no CategoryValue
        chair = AssetService.register(self.w.eng_coord, {
            "name": "Office chair", "description": "Mesh chair", "category": furniture, "condition": "Good",
            "tags": "", "quantity": 4, "estimated_value": Decimal("450"), "weight_kg": Decimal("12")})
        AssetService.publish(self.w.eng_coord, chair)
        complete_transfer(self.w, quantity=4, asset=chair)
        complete_transfer(self.w, quantity=2)  # the oscilloscopes: electronics, with a factor
        totals, rows = SustainabilityCalculator().calculate()
        self.assertEqual(totals["waste_kg"], Decimal("53.2"))   # 48 kg of chairs + 5.2 kg of oscilloscopes
        self.assertEqual(totals["co2e_kg"], Decimal("119.18"))  # only the oscilloscopes: 5.2 x 22.92
        self.assertEqual([row["transfer"].asset for row in rows if row["co2e"] is None], [chair])
        self.client.force_login(self.w.fac_rep)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Missing data · 1 transfer(s) left out of CO2e")


class NotificationTests(TestCase):
    def setUp(self):
        self.w = build_sample_world()

    def test_unread_count_is_shown_in_the_header_and_can_be_cleared(self):
        RequestService.submit(self.w.physics_rep, self.w.scope, 1, "Lab", NEXT_MONTH)
        self.client.force_login(self.w.eng_coord)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.context["unread_count"], 1)
        self.assertContains(response, '<span class="badge">1</span>', html=True)
        self.client.post(reverse("notifications_read"))
        self.assertEqual(self.client.get(reverse("home")).context["unread_count"], 0)
