from __future__ import annotations

import hashlib
import os
from unittest import TestCase
from unittest.mock import patch

from content.services.payments import (
    HttpPayFastVerificationGateway,
    _itn_parameter_string,
    generate_payfast_itn_signature,
    generate_payfast_signature,
)


@patch.dict(
    os.environ,
    {
        "PAYFAST_MODE": "sandbox",
        "PAYFAST_ENV": "sandbox",
        "PAYFAST_MERCHANT_ID": "10004002",
        "PAYFAST_MERCHANT_KEY": "synthetic-only",
        "PAYFAST_PASSPHRASE": "synthetic-test-salt",
    },
)
class PayFastITNCanonicalizationTests(TestCase):
    def fixture(self):
        fields = {
            "m_payment_id": "PF-isolated-test-reference",
            "pf_payment_id": "SYNTHETIC-PF-0001",
            "payment_status": "COMPLETE",
            "item_name": "Amaris sample",
            "item_description": "",
            "amount_gross": "250.00",
            "amount_fee": "-5.00",
            "amount_net": "245.00",
            "custom_str1": "",
            "custom_str2": "grade-12",
            "custom_str3": "",
            "email_address": "student@example.test",
            "merchant_id": "10004002",
        }
        fields["signature"] = generate_payfast_itn_signature(fields, "synthetic-test-salt")
        return fields

    def test_posted_blank_values_are_signed_in_itn(self):
        payload = self.fixture()
        body = _itn_parameter_string(payload, "synthetic-test-salt")
        self.assertIn("item_description=&", body)
        self.assertIn("custom_str1=&", body)
        self.assertIn("custom_str3=&", body)
        self.assertNotIn("signature=", body)
        self.assertEqual(hashlib.md5(body.encode("utf-8")).hexdigest(), payload["signature"])
        self.assertNotEqual(
            generate_payfast_signature(payload, "synthetic-test-salt"),
            payload["signature"],
        )

    @patch("content.services.payments.urlopen")
    def test_provider_validation_receives_exact_unsigned_itn_body(self, fake_urlopen):
        fake_urlopen.return_value.__enter__.return_value.read.return_value = b"VALID"
        payload = self.fixture()
        approved = HttpPayFastVerificationGateway().verify_notification(payload)
        self.assertTrue(approved)
        request = fake_urlopen.call_args.args[0]
        posted = request.data.decode("utf-8")
        self.assertIn("custom_str1=&", posted)
        self.assertIn("item_description=&", posted)
        self.assertNotIn("signature=", posted)
        self.assertNotIn("passphrase=", posted)
        self.assertEqual(posted, _itn_parameter_string(payload))

    @patch("content.services.payments.urlopen")
    def test_bad_signature_rejected_without_network_call(self, fake_urlopen):
        payload = self.fixture()
        payload["signature"] = "0" * 32
        self.assertFalse(HttpPayFastVerificationGateway().verify_notification(payload))
        fake_urlopen.assert_not_called()

    @patch("content.services.payments.urlopen")
    def test_provider_invalid_rejected_even_with_correct_signature(self, fake_urlopen):
        fake_urlopen.return_value.__enter__.return_value.read.return_value = b"INVALID"
        payload = self.fixture()
        self.assertFalse(HttpPayFastVerificationGateway().verify_notification(payload))
