"""Offline tests for the scoped Supabase Auth template updater."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import pathlib
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "configure_supabase_auth_otp.py"
SPEC = importlib.util.spec_from_file_location("auth_otp_updater", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class SupabaseAuthOtpTests(unittest.TestCase):
    def test_templates_include_real_supabase_otp_placeholder(self):
        desired = module.desired_config()
        self.assertEqual(desired["mailer_otp_length"], 6)
        self.assertEqual(desired["mailer_otp_exp"], 600)
        self.assertIs(desired["mailer_autoconfirm"], False)
        self.assertIn("{{ .Token }}", desired["mailer_templates_confirmation_content"])
        self.assertIn("{{ .Token }}", desired["mailer_templates_magic_link_content"])
        self.assertIn("{{ .ConfirmationURL }}", desired["mailer_templates_magic_link_content"])
        self.assertNotIn("{{ .SiteURL }}/auth/confirm", desired["mailer_templates_magic_link_content"])
        self.assertNotIn("123456", desired["mailer_templates_confirmation_content"])
        self.assertIn("{{ .Token }}", desired["mailer_templates_recovery_content"])
        self.assertIn("{{ .TokenHash }}", desired["mailer_templates_recovery_content"])
        self.assertIn("{{ .SiteURL }}/reset-password/verify?token_hash={{ .TokenHash }}", desired["mailer_templates_recovery_content"])
        self.assertNotIn("{{ .RedirectTo }}", desired["mailer_templates_recovery_content"])
        self.assertNotIn("localhost", desired["mailer_templates_recovery_content"].lower())
        self.assertNotIn("{{ .ConfirmationURL }}", desired["mailer_templates_recovery_content"])
        self.assertEqual(desired["mailer_subjects_recovery"], "Amaris | Reset your password")

    def test_check_requires_templates_confirmation_and_smtp(self):
        configured = module.desired_config() | {
            "site_url": "https://amaris-mathematics-academy-live-students.onrender.com",
            "smtp_host": "smtp.example.test",
            "smtp_admin_email": "verified@example.test",
            "external_email_enabled": True,
        }
        self.assertTrue(all(module.status_of(configured).values()))
        configured["mailer_otp_length"] = 8
        configured["smtp_host"] = None
        failures = module.status_of(configured)
        self.assertFalse(failures["mailer_otp_length"])
        self.assertFalse(failures["smtp_host_configured"])

    def test_apply_never_mutates_without_auth_smtp(self):
        output = io.StringIO()
        with (
            patch.dict(os.environ, {"SUPABASE_ACCESS_TOKEN": "synthetic-only"}, clear=True),
            patch.object(module, "request_config", return_value={"smtp_host": None}) as api,
            contextlib.redirect_stderr(output),
        ):
            outcome = module.main(["--project-ref", "epkcuseloinygkakxxdu", "--mode", "apply"])
        self.assertEqual(outcome, 3)
        self.assertEqual(api.call_count, 1)
        self.assertIn("SMTP", output.getvalue())
        self.assertNotIn("synthetic-only", output.getvalue())

    def test_apply_patches_only_otp_related_settings_and_verifies(self):
        configured = module.desired_config() | {
            "site_url": "https://amaris-mathematics-academy-live-students.onrender.com",
            "smtp_host": "smtp.example.test",
            "smtp_admin_email": "verified@example.test",
            "external_email_enabled": True,
        }
        out = io.StringIO()
        with (
            patch.dict(os.environ, {"SUPABASE_ACCESS_TOKEN": "synthetic-only"}, clear=True),
            patch.object(module, "request_config", side_effect=[configured, {}, configured]) as api,
            contextlib.redirect_stdout(out),
        ):
            outcome = module.main(["--project-ref", "epkcuseloinygkakxxdu", "--mode", "apply"])
        self.assertEqual(outcome, 0)
        self.assertEqual([call.args[0] for call in api.call_args_list], ["GET", "PATCH", "GET"])
        patch_payload = api.call_args_list[1].args[3]
        self.assertEqual(patch_payload["mailer_otp_length"], 6)
        self.assertNotIn("smtp_pass", patch_payload)
        self.assertNotIn("smtp_host", patch_payload)
        self.assertNotIn("synthetic-only", out.getvalue())
        self.assertNotIn("smtp.example.test", out.getvalue())

    def test_refuse_wrong_or_localhost_production_site_url_before_patch(self):
        for site_url in (
            "http://localhost:3000",
            "https://localhost:3000",
            "https://other.example.test",
        ):
            config = module.desired_config() | {
                "site_url": site_url,
                "smtp_host": "smtp.example.test",
                "smtp_admin_email": "verified@example.test",
                "external_email_enabled": True,
            }
            with (
                self.subTest(site_url=site_url),
                patch.dict(os.environ, {"SUPABASE_ACCESS_TOKEN": "synthetic-only"}, clear=True),
                patch.object(module, "request_config", return_value=config) as api,
                contextlib.redirect_stderr(io.StringIO()),
            ):
                result = module.main(["--project-ref", "epkcuseloinygkakxxdu", "--mode", "apply"])
            self.assertEqual(result, 3)
            self.assertEqual(api.call_count, 1, "Never PATCH a project with an invalid Auth Site URL")

    def test_missing_token_fails_without_network(self):
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(module.main(["--project-ref", "epkcuseloinygkakxxdu"]), 2)


if __name__ == "__main__":
    unittest.main()
