"""Regression checks for the existing approved Amaris formal letterhead."""

from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from content.services.official_letterhead import official_letterhead_html


class OfficialLetterheadTests(SimpleTestCase):
    @override_settings(PUBLIC_SITE_URL="https://academy.example.test")
    @patch("content.services.official_letterhead.SiteSettings.objects.first", return_value=None)
    def test_formal_email_has_brand_identity_and_safe_html(self, _site):
        html = official_letterhead_html(
            heading="Official enrolment notice",
            body_lines=["Welcome <script>alert('bad')</script>", "Course: Mathematics"],
            reference="AMARIS-TEST-123",
        )
        self.assertIn("Amaris Mathematics Academy", html)
        self.assertIn("MATHEMATICS · LEARNING · PROGRESS", html)
        self.assertIn("amaris-academy-icon-192.png", html)
        self.assertIn("27 Tshivhase Street", html)
        self.assertIn("071 415 6665", html)
        self.assertIn("bethuelmoukangwe8@gmail.com", html)
        self.assertIn("https://academy.example.test", html)
        self.assertIn("AMARIS-TEST-123", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)
        self.assertIn("Professional mathematics education and learner support", html)

    @override_settings(PUBLIC_SITE_URL="http://localhost:3000")
    @patch("content.services.official_letterhead.SiteSettings.objects.first", return_value=None)
    def test_formal_letterhead_never_links_to_localhost(self, _site):
        html = official_letterhead_html(heading="Account notice", body_lines=["Secure notice"])
        self.assertNotIn("localhost:3000", html)
        self.assertIn("https://amaris-mathematics-academy-live-students.onrender.com", html)
