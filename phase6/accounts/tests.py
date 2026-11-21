"""Tests for login (C1)."""
from django.test import TestCase
from django.urls import reverse


class LoginTests(TestCase):
    def test_pages_need_a_login(self):
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, reverse("login") + "?next=/")
