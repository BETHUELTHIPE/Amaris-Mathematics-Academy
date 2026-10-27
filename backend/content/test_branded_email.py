"""Regression checks: official letterhead, safe escaping and preserved notifications."""
from unittest.mock import patch

from django.test import SimpleTestCase

from content.services.branded_email import render_branded_email


class ProfessionalEmailLetterheadTests(SimpleTestCase):
    @patch("content.services.branded_email.SiteSettings.objects.first", return_value=None)
    def test_official_letterhead_contacts_logo_and_content(self, _site):
        html = render_branded_email(
            "Class booking confirmed",
            ["Your Zoom class starts at 19:00 SAST.", "Topic: Algebra"],
            reference="AMARIS-BOOK-001",
        )
        self.assertIn("Amaris Mathematics Academy", html)
        self.assertIn("Bethuel Moukangwe", html)
        self.assertIn("27 Tshivhase Street", html)
        self.assertIn("071 415 6665", html)
        self.assertIn("amaris-academy-icon-192.png", html)
        self.assertIn("Mathematics", html)
        self.assertIn("Class booking confirmed", html)
        self.assertIn("AMARIS-BOOK-001", html)
        self.assertIn("Your Zoom class starts at 19:00 SAST.", html)
        self.assertIn("#ffcc66", html)

    @patch("content.services.branded_email.SiteSettings.objects.first", return_value=None)
    def test_untrusted_subject_lines_and_reference_are_escaped(self, _site):
        html = render_branded_email(
            "<script>alert('malicious')</script>",
            ["<img src=x onerror=alert(1)>", "Escaped & safe"],
            reference='"><script>steal()</script>',
        )
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&lt;img", html)
        self.assertIn("Escaped &amp; safe", html)

    @patch("content.services.branded_email.SiteSettings.objects.first", return_value=None)
    def test_long_multiline_email_keeps_line_breaks_without_raw_html(self, _site):
        html = render_branded_email(
            "Your enquiry",
            ["First line\nSecond line\n<b>Not HTML</b>"],
        )
        self.assertIn("white-space:pre-line", html)
        self.assertIn("First line\nSecond line", html)
        self.assertIn("&lt;b&gt;Not HTML&lt;/b&gt;", html)
