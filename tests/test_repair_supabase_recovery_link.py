"""Protect branded hosted recovery template during canonical-link repair."""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
path = ROOT / "scripts" / "repair_supabase_recovery_link.py"
spec = importlib.util.spec_from_file_location("repair_recovery_link", path)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RecoveryLinkRepairTests(unittest.TestCase):
    def test_preserves_professional_letterhead_and_changes_only_bad_href(self):
        before = (
            '<div class="letterhead"><b>Amaris Mathematics Academy</b>'
            '<p>27 Tshivhase Street · Pretoria · Tel 071 415 6665</p></div>'
            '<p>Six-digit password reset: {{ .Token }}</p>'
            '<a style="color:blue" href="{{ .RedirectTo }}?token_hash={{ .TokenHash }}">'
            'continue securely to your reset page</a>'
            '<footer>ACCOUNT SECURITY — PASSWORD RESET</footer>'
        )
        after = module.repair_link_preserving_letterhead(before)
        expected = before.replace("{{ .RedirectTo }}?token_hash={{ .TokenHash }}", module.TARGET_HREF)
        self.assertEqual(after, expected)
        self.assertIn("27 Tshivhase Street", after)
        self.assertIn("ACCOUNT SECURITY — PASSWORD RESET", after)
        self.assertIn("{{ .Token }}", after)
        self.assertNotIn("{{ .RedirectTo }}", after)

    def test_repairs_hardcoded_localhost_and_never_adds_an_external_origin(self):
        original = '<b>Academy</b>{{ .Token }}<a href="http://localhost:3000/?token_hash={{ .TokenHash }}">Continue</a>'
        fixed = module.repair_link_preserving_letterhead(original)
        self.assertIn(module.TARGET_HREF, fixed)
        self.assertNotIn("localhost", fixed)

    def test_idempotent_link_never_overwrites_letterhead(self):
        html = '{{ .Token }}<h1>Amaris</h1><a href="' + module.TARGET_HREF + '">Continue</a>'
        self.assertEqual(module.repair_link_preserving_letterhead(html), html)

    def test_refuses_missing_or_multiple_recovery_links_and_unexpected_domains(self):
        for html in (
            "{{ .Token }}<h1>No links {{ .TokenHash }}</h1>",
            '{{ .Token }}<a href="{{ .RedirectTo }}?token_hash={{ .TokenHash }}">a</a>'
            '<a href="{{ .RedirectTo }}?token_hash={{ .TokenHash }}">b</a>',
            '{{ .Token }}<a href="https://evil.example/?token_hash={{ .TokenHash }}">x</a>',
        ):
            with self.subTest(html=html[:25]), self.assertRaises(ValueError):
                module.repair_link_preserving_letterhead(html)

    def test_requires_canonical_public_https_site_url_for_production(self):
        for url in ("http://localhost:3000", "https://localhost:3000",
                    "https://example.com", "https://amaris-mathematics-academy-staging-x4ax.onrender.com"):
            self.assertFalse(module.safe_site(url, module.PRODUCTION_REF))
        self.assertTrue(module.safe_site(module.PRODUCTION_SITE, module.PRODUCTION_REF))
        self.assertTrue(module.safe_site("https://amaris-mathematics-academy-staging-x4ax.onrender.com", module.STAGING_REF))

    def test_recovery_code_remains_user_supplied_in_real_form(self):
        src = (ROOT / "frontend/app/reset-password/verify/page.tsx").read_text(encoding="utf-8")
        self.assertIn('name="token"', src)
        self.assertIn('name="email"', src)


if __name__ == "__main__":
    unittest.main()
