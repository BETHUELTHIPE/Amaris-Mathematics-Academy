from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from content.payfast_views import PayFastITNView
from content.services.payments import NotificationResult


class PayFastITNDiagnosticsTests(SimpleTestCase):
    def post(self, source="144.126.193.139"):
        request = APIRequestFactory().post(
            "/api/v1/payfast/itn/",
            {"m_payment_id": "LCB-private-reference", "email_address": "private@example.test", "signature": "secret"},
            REMOTE_ADDR=source,
        )
        return PayFastITNView.as_view()(request)

    @patch("content.payfast_views.process_live_class_notification")
    def test_untrusted_source_is_rejected_and_logged_without_private_fields(self, process):
        with self.assertLogs("amaris.payfast", level="INFO") as logs:
            response = self.post(source="192.0.2.10")
        self.assertEqual(response.status_code, 403)
        process.assert_not_called()
        self.assertIn("untrusted_source", " ".join(logs.output))
        self.assert_private_data_absent(logs.output)

    @patch("content.payfast_views.process_live_class_notification")
    def test_accepted_rejected_and_retryable_results_have_distinct_outcomes(self, process):
        cases = (
            (NotificationResult(True, "confirmed"), 200, "accepted"),
            (NotificationResult(False, "pending_payment", reason="invalid_callback"), 400, "rejected"),
            (
                NotificationResult(False, "pending_payment", reason="verification_timeout", retryable=True),
                503,
                "retryable",
            ),
        )
        for result, status, outcome in cases:
            with self.subTest(outcome=outcome), patch.dict("os.environ", {"PAYFAST_ALLOWED_NETWORKS": ""}):
                process.return_value = result
                with self.assertLogs("amaris.payfast", level="INFO") as logs:
                    response = self.post()
                self.assertEqual(response.status_code, status)
                self.assertIn(f"payfast_itn {outcome}", " ".join(logs.output))
                self.assert_private_data_absent(logs.output)

    def assert_private_data_absent(self, output):
        rendered = " ".join(output)
        for private in ("private-reference", "private@example.test", "secret", "144.126.193.139", "192.0.2.10"):
            self.assertNotIn(private, rendered)
