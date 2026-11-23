"""Tests for login (C1) and the seed command."""
import io

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from assets.models import Asset
from resource_requests.models import Request
from sustainability.services import SustainabilityCalculator


class LoginTests(TestCase):
    def test_pages_need_a_login(self):
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, reverse("login") + "?next=/")


class SeedTests(TestCase):
    def test_seed_loads_users_assets_requests_and_dashboard_numbers(self):
        call_command("seed", stdout=io.StringIO())
        self.assertEqual(User.objects.count(), 7)
        self.assertTrue(User.objects.get(username="admin").check_password("demo1234"))
        scope = Asset.objects.get(code="A-2026-0412")
        self.assertEqual((scope.name, scope.quantity, scope.condition), ("Digital oscilloscope", 2, "Good"))
        states = set(Request.objects.values_list("state", flat=True))
        self.assertEqual(states, {"Open", "Submitted", "Released", "Approved", "In Transfer", "Completed", "Rejected"})
        totals, rows = SustainabilityCalculator().calculate()
        # CO2e counts only the 2 monitors: 9.0 kg x 22.92 = 206.3. The 4 chairs (Furniture) have no
        # emission factor, so they are left out of CO2e and listed as missing data (FR-13.8).
        self.assertEqual(SustainabilityCalculator.display(totals),
                         {"items_reused": "6", "cost_avoided": "3,100", "waste_kg": "57.0", "co2e_kg": "206.3"})
        missing = [row for row in rows if row["co2e"] is None]
        self.assertEqual([row["transfer"].asset.name for row in missing], ["Ergonomic office chair"])
