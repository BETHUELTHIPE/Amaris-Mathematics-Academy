from __future__ import annotations

import os
from unittest.mock import patch

from django.test import SimpleTestCase

from content.services.payments import (
    PAYFAST_SANDBOX_VALIDATE_URL,
    HttpPayFastVerificationGateway,
    PaymentSecurityError,
    _payfast_mode,
    generate_payfast_signature,
)


class PayFastEnvironmentTests(SimpleTestCase):
    def test_environment_names_resolve_consistently(self):
        cases = (
            ({}, "sandbox"),
            ({"PAYFAST_ENV": "sandbox"}, "sandbox"),
            ({"PAYFAST_ENV": "live"}, "live"),
            ({"PAYFAST_MODE": "live"}, "live"),
            ({"PAYFAST_MODE": " LIVE ", "PAYFAST_ENV": "live"}, "live"),
            ({"PAYFAST_MODE": "", "PAYFAST_ENV": "sandbox"}, "sandbox"),
        )
        for environment, expected in cases:
            with self.subTest(environment=environment), patch.dict(os.environ, environment, clear=True):
                self.assertEqual(_payfast_mode(), expected)

    def test_invalid_or_conflicting_environments_fail_closed(self):
        cases = (
            {"PAYFAST_ENV": "production"},
            {"PAYFAST_MODE": "test"},
            {"PAYFAST_MODE": "live", "PAYFAST_ENV": "sandbox"},
            {"PAYFAST_MODE": "sandbox", "PAYFAST_ENV": "live"},
        )
        for environment in cases:
            with self.subTest(environment=environment), patch.dict(os.environ, environment, clear=True):
                with self.assertRaises(PaymentSecurityError):
                    _payfast_mode()


@patch.dict(
    os.environ,
    {
        "PAYFAST_MODE": "",
        "PAYFAST_ENV": "sandbox",
        "PAYFAST_MERCHANT_ID": "99990001",
        "PAYFAST_MERCHANT_KEY": "synthetic-key",
        "PAYFAST_PASSPHRASE": "synthetic-test-passphrase",
    },
)
class PayFastHttpVerifierTests(SimpleTestCase):
    def payload(self, merchant_id="99990001"):
        fields = {
            "merchant_id": merchant_id,
            "m_payment_id": "PF-synthetic-config-test",
            "payment_status": "COMPLETE",
            "amount_gross": "10.00",
        }
        fields["signature"] = generate_payfast_signature(fields, "synthetic-test-passphrase")
        return fields

    @patch("content.services.payments.urlopen")
    def test_wrong_or_missing_merchant_is_rejected_before_network_validation(self, urlopen):
        for merchant_id in ("99990002", ""):
            self.assertFalse(HttpPayFastVerificationGateway().verify_notification(self.payload(merchant_id)))
        urlopen.assert_not_called()

    @patch("content.services.payments.urlopen")
    def test_env_alias_selects_sandbox_validation_and_requires_valid_response(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b"VALID"
        self.assertTrue(HttpPayFastVerificationGateway().verify_notification(self.payload()))
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, PAYFAST_SANDBOX_VALIDATE_URL)
        self.assertNotIn(b"passphrase", request.data)
        response.read.return_value = b"INVALID"
        self.assertFalse(HttpPayFastVerificationGateway().verify_notification(self.payload()))

    @patch("content.services.payments.urlopen")
    def test_invalid_signature_never_reaches_provider(self, urlopen):
        payload = self.payload()
        payload["signature"] = "0" * 32
        self.assertFalse(HttpPayFastVerificationGateway().verify_notification(payload))
        urlopen.assert_not_called()
