"""Tests for login (C1), the pages real users see, and the seed command."""
import io
from datetime import date, timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from accounts.sample_data import build_sample_world
from ai.gateway import AIGateway
from ai.report_generator import ReportGenerator
from assets.models import Asset
from resource_requests.models import Request
from resource_requests.services import RequestService
from sustainability.services import SustainabilityCalculator

# Text that belongs in our design documents, never on a page.
INTERNAL_TEXT = ["FR-", "SAF-", "Section ", "Table 1", "demo1234", "README", "rank rules", "AI output #",
                 "When AI is unavailable", "gemini"]


class LoginTests(TestCase):
    def test_pages_need_a_login(self):
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, reverse("login") + "?next=/")

    def test_login_page_does_not_show_demo_logins(self):
        response = self.client.get(reverse("login"))
        self.assertNotContains(response, "demo1234")
        self.assertNotContains(response, "README")


@override_settings(GEMINI_API_KEY="")
class UserFacingPageTests(TestCase):
    def setUp(self):
        self.w = build_sample_world()
        self.need = RequestService.submit_need(self.w.physics_rep, self.w.lab, 2, "Oscilloscopes for a lab",
                                               date.today() + timedelta(days=30))

    def assert_clean(self, response):
        self.assertEqual(response.status_code, 200)
        for text in INTERNAL_TEXT:
            self.assertNotContains(response, text)

    def test_pages_show_no_design_references_or_model_names(self):
        pages = {
            self.w.physics_rep: [reverse("home"), reverse("asset_list"), reverse("need_create"),
                                 reverse("asset_detail", args=[self.w.scope.pk]), reverse("my_requests"),
                                 reverse("request_detail", args=[self.need.pk]), reverse("dashboard"),
                                 reverse("report_table"), reverse("summary_list"), reverse("notifications")],
            self.w.eng_coord: [reverse("asset_create"), reverse("my_assets"), reverse("tasks")],
        }
        for user, urls in pages.items():
            self.client.force_login(user)
            for url in urls:
                with self.subTest(url=url):
                    self.assert_clean(self.client.get(url))

        # The AI pages, once with the rule-based fallback and once with a (fake) AI answer.
        self.client.force_login(self.w.physics_rep)
        self.assert_clean(self.client.get(reverse("request_matches", args=[self.need.pk])))
        with patch.object(AIGateway, "call_model", return_value=({"reasons": ["Fits well."]}, "OK")):
            page = self.client.get(reverse("request_matches", args=[self.need.pk]))
        self.assert_clean(page)
        self.assertContains(page, "AI-ranked")  # the badge stays

        self.client.force_login(self.w.eng_coord)
        suggestion = {"category": "Lab Equipment", "category_confidence": 0.9, "condition": "Good",
                      "condition_confidence": 0.9, "tags": ["oscilloscope"], "tags_confidence": 0.9,
                      "confidence": 0.9, "reason": "Looks like lab equipment."}
        with patch.object(AIGateway, "call_model", return_value=(suggestion, "OK")):
            page = self.client.post(reverse("asset_create"), {"name": "Oscilloscope", "description": "Bench scope",
                                                              "action": "suggest"})
        self.assert_clean(page)
        self.assertContains(page, "AI suggestion")  # the label stays

        self.client.force_login(self.w.admin)
        report = ReportGenerator().generate(self.w.admin, date.today().replace(day=1), date.today())
        page = self.client.get(reverse("summary_detail", args=[report.pk]))
        self.assert_clean(page)
        self.assertContains(page, "AI unavailable, rule-based result")  # the real fallback label stays
        self.assertContains(page, "numbers in the draft")                # the number check stays

    def test_missing_page_uses_our_404_page(self):
        self.client.force_login(self.w.physics_rep)
        response = self.client.get("/no-such-page/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Page not found", status_code=404)
        self.assertContains(response, "Back to home", status_code=404)

    def test_server_error_page_renders_without_a_user(self):
        # Django renders 500.html without the request or user, so it must work on its own.
        html = render_to_string("500.html")
        self.assertIn("Something went wrong", html)
        self.assertIn("Back to home", html)


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
