"""Safety tests: no account creation or email probe without explicit opt-in."""

import os
import unittest
from unittest.mock import patch

import staging_fixture_setup as fixture


class StagingFixtureSafetyTests(unittest.TestCase):
    def test_preflight_rejects_wrong_branch_before_network(self):
        with patch.dict(os.environ, {
            "GITHUB_REPOSITORY": "BETHUELTHIPE/Amaris-Mathematics-Academy",
            "GITHUB_REF": "refs/heads/main",
            "PAYFAST_MODE": "sandbox",
        }, clear=True), patch.object(fixture, "render_json", side_effect=AssertionError("called")):
            with self.assertRaisesRegex(RuntimeError, "incorrect staging-fixture branch"):
                fixture.preflight()

    def test_preflight_rejects_live_payfast_before_network(self):
        with patch.dict(os.environ, {
            "GITHUB_REPOSITORY": "BETHUELTHIPE/Amaris-Mathematics-Academy",
            "GITHUB_REF": "refs/heads/test/staging-fixture-setup-20261020",
            "PAYFAST_MODE": "live",
        }, clear=True), patch.object(fixture, "render_json", side_effect=AssertionError("called")):
            with self.assertRaisesRegex(RuntimeError, "PayFast sandbox-only"):
                fixture.preflight()

    def test_push_cannot_create_staging_identities_even_with_opt_in(self):
        with patch.dict(os.environ, {
            "GITHUB_EVENT_NAME": "push",
            "STAGING_FIXTURE_BOOTSTRAP_CONFIRM": "CREATE_STAGING_QA_USERS",
            "STAGING_FIXTURE_ACTION": "CREATE_STAGING_QA_USERS",
            "STAGING_SUPABASE_SERVICE_ROLE_KEY": "sample-not-a-real-key",
        }, clear=True), patch.object(fixture, "http_json", side_effect=AssertionError("called")):
            with self.assertRaisesRegex(RuntimeError, "manual GitHub"):
                fixture.execute({})

    def test_manual_create_requires_both_approvals(self):
        with patch.dict(os.environ, {
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "STAGING_FIXTURE_ACTION": "CREATE_STAGING_QA_USERS",
        }, clear=True):
            with self.assertRaisesRegex(RuntimeError, "environment opt-in"):
                fixture.execute({})
        with patch.dict(os.environ, {
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "STAGING_FIXTURE_BOOTSTRAP_CONFIRM": "CREATE_STAGING_QA_USERS",
        }, clear=True):
            with self.assertRaisesRegex(RuntimeError, "select CREATE_STAGING"):
                fixture.execute({})

    def test_missing_protected_auth_key_cannot_fall_back_to_render(self):
        with patch.dict(os.environ, {
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "STAGING_FIXTURE_ACTION": "CREATE_STAGING_QA_USERS",
            "STAGING_FIXTURE_BOOTSTRAP_CONFIRM": "CREATE_STAGING_QA_USERS",
        }, clear=True):
            with self.assertRaisesRegex(RuntimeError, "STAGING_SUPABASE_SERVICE_ROLE_KEY"):
                fixture.execute({"SUPABASE_SERVICE_ROLE_KEY": "fake-render-key"})

    def test_smtp_probe_rejects_push_and_missing_secret(self):
        with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "push"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "manual dispatch"):
                fixture.smtp_auth_only({})
        with patch.dict(os.environ, {
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "STAGING_FIXTURE_ACTION": "SMTP_AUTH_ONLY",
        }, clear=True):
            with self.assertRaisesRegex(RuntimeError, "STAGING_SMTP_PASSWORD"):
                fixture.smtp_auth_only({})

    def test_smtp_probe_checks_render_and_github_secrets_match_without_network(self):
        with patch.dict(os.environ, {
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "STAGING_FIXTURE_ACTION": "SMTP_AUTH_ONLY",
            "STAGING_SMTP_PASSWORD": "private-test-placeholder",
        }, clear=True), patch.object(fixture.smtplib, "SMTP", side_effect=AssertionError("called")):
            vars = {
                "EMAIL_HOST": "smtp.gmail.com", "EMAIL_PORT": "587",
                "EMAIL_USE_TLS": "true", "EMAIL_USE_SSL": "false",
                "EMAIL_HOST_USER": fixture.EXPECTED_STUDENT,
                "DEFAULT_FROM_EMAIL": fixture.EXPECTED_STUDENT,
                "EMAIL_HOST_PASSWORD": "a-different-placeholder",
            }
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                fixture.smtp_auth_only(vars)


if __name__ == "__main__":
    unittest.main()
