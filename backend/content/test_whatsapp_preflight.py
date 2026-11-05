"""Mocked read-only verification: never contacts Meta or sends WhatsApp."""

import io
import json
import os
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from content.management.commands import check_whatsapp_staging

MOCK_CONFIG = {
    "WHATSAPP_NOTIFICATIONS_ENABLED": "false",
    "WHATSAPP_APP_SECRET": "staging-test-secret",
    "WHATSAPP_WEBHOOK_VERIFY_TOKEN": "staging-test-verify-token",
    "WHATSAPP_GRAPH_API_VERSION": "v23.0",
    "WHATSAPP_WABA_ID": "1000123456789",
    "WHATSAPP_CLOUD_TOKEN": "test-only-never-real",
    "WHATSAPP_PHONE_NUMBER_ID": "123456789",
    "WHATSAPP_TEMPLATE_LANGUAGE": "en",
    "WHATSAPP_CONFIRMATION_TEMPLATE": "amaris_booking_confirmation",
    "WHATSAPP_REMINDER_TEMPLATE": "amaris_class_reminder",
}


def meta_response(confirmation_category="UTILITY", reminder_status="APPROVED"):
    return io.BytesIO(
        json.dumps(
            {
                "data": [
                    {
                        "name": "amaris_booking_confirmation",
                        "language": "en",
                        "status": "APPROVED",
                        "category": confirmation_category,
                    },
                    {
                        "name": "amaris_class_reminder",
                        "language": "en",
                        "status": reminder_status,
                        "category": "UTILITY",
                    },
                ]
            }
        ).encode("utf-8")
    )


@override_settings(WHATSAPP_NOTIFICATIONS_ENABLED=False)
@patch.dict(os.environ, MOCK_CONFIG)
class WhatsAppStagingPreflightTests(SimpleTestCase):
    def test_local_webhook_challenge_and_signature(self):
        output = io.StringIO()
        call_command("check_whatsapp_staging", "--webhook-only", stdout=output)
        self.assertIn("PASS", output.getvalue())
        self.assertNotIn(MOCK_CONFIG["WHATSAPP_APP_SECRET"], output.getvalue())

    @patch.object(check_whatsapp_staging, "urlopen")
    def test_direct_template_check_passes_only_for_two_approved_utility_templates(self, http):
        http.return_value = meta_response()
        output = io.StringIO()
        call_command("check_whatsapp_staging", stdout=output)
        self.assertIn("Both Meta Utility templates verified", output.getvalue())
        self.assertEqual(http.call_count, 1)
        request = http.call_args.args[0]
        self.assertIn("/message_templates?", request.full_url)
        self.assertNotIn(MOCK_CONFIG["WHATSAPP_CLOUD_TOKEN"], request.full_url)

    @patch.object(check_whatsapp_staging, "urlopen")
    def test_recategorised_marketing_confirmation_is_blocked(self, http):
        http.return_value = meta_response(confirmation_category="MARKETING")
        with self.assertRaisesRegex(CommandError, "both templates must be APPROVED / UTILITY"):
            call_command("check_whatsapp_staging", stdout=io.StringIO())

    @patch.object(check_whatsapp_staging, "urlopen")
    def test_unapproved_reminder_is_blocked(self, http):
        http.return_value = meta_response(reminder_status="PENDING")
        with self.assertRaisesRegex(CommandError, "both templates must be APPROVED / UTILITY"):
            call_command("check_whatsapp_staging", stdout=io.StringIO())

    @patch.object(check_whatsapp_staging, "urlopen")
    def test_missing_reminder_is_blocked(self, http):
        http.return_value = io.BytesIO(
            json.dumps(
                {
                    "data": [
                        {
                            "name": "amaris_booking_confirmation",
                            "status": "APPROVED",
                            "category": "UTILITY",
                            "language": "en",
                        }
                    ]
                }
            ).encode("utf-8")
        )
        with self.assertRaisesRegex(CommandError, "both templates must be APPROVED / UTILITY"):
            call_command("check_whatsapp_staging", stdout=io.StringIO())

    @override_settings(WHATSAPP_NOTIFICATIONS_ENABLED=True)
    @patch.object(check_whatsapp_staging, "urlopen")
    def test_refuses_to_run_when_live_sending_enabled(self, http):
        with self.assertRaisesRegex(CommandError, "Refusing preflight"):
            call_command("check_whatsapp_staging", stdout=io.StringIO())
        http.assert_not_called()

    @patch.dict(os.environ, {"WHATSAPP_APP_SECRET": ""})
    def test_missing_webhook_secret_fails_closed(self):
        with self.assertRaisesRegex(CommandError, "WHATSAPP_APP_SECRET"):
            call_command("check_whatsapp_staging", "--webhook-only", stdout=io.StringIO())
