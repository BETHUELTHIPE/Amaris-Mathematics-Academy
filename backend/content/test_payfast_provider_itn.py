"""Real-provider-shaped ITN signature regression tests; no external payment or secrets."""

from __future__ import annotations

import hashlib
from unittest.mock import patch
from urllib.parse import quote_plus

from django.test import SimpleTestCase

from content.services.payments import HttpPayFastVerificationGateway, generate_payfast_signature


class _ProviderResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b"VALID"


def _provider_payload() -> dict[str, str]:
    # Follow the actual PayFast notification field order, including empty values.
    data = {
        "m_payment_id": "LCB-integration-synthetic",
        "pf_payment_id": "111111111",
        "payment_status": "COMPLETE",
        "item_name": "Mathematics ~ Maths",
        "item_description": "",
        "amount_gross": "250.00",
        "amount_fee": "-5.75",
        "amount_net": "244.25",
        "custom_str1": "00000000-0000-4000-8000-000000000001",
        "custom_str2": "",
        "custom_str3": "",
        "name_first": "Amaris",
        "name_last": "Student",
        "email_address": "synthetic@example.invalid",
        "merchant_id": "10000100",
    }
    signature_source = "&".join(
        f"{key}={quote_plus(value, safe='').replace('~', '%7E')}" for key, value in data.items()
    )
    signature_source += "&passphrase=" + quote_plus("synthetic-passphrase", safe="").replace("~", "%7E")
    data["signature"] = hashlib.md5(signature_source.encode("utf-8"), usedforsecurity=False).hexdigest()
    return data


class PayFastProviderITNTests(SimpleTestCase):
    def verify(self, payload):
        with (
            patch(
                "content.services.payments._payfast_credentials",
                return_value=("10000100", "merchant-key", "synthetic-passphrase"),
            ),
            patch("content.services.payments._payfast_mode", return_value="sandbox"),
            patch("content.services.payments.urlopen", return_value=_ProviderResponse()) as request,
        ):
            accepted = HttpPayFastVerificationGateway().verify_notification(payload)
        return accepted, request

    def test_received_fields_include_empty_values_and_php_encoded_tilde(self):
        valid, request = self.verify(_provider_payload())
        self.assertTrue(valid)
        request.assert_called_once()
        outgoing = request.call_args.args[0]
        self.assertIn(b"item_description=", outgoing.data)
        self.assertIn(b"custom_str2=&custom_str3=", outgoing.data)
        self.assertIn(b"Mathematics+%7E+Maths", outgoing.data)
        self.assertNotIn(b"passphrase", outgoing.data)
        self.assertNotIn(b"signature", outgoing.data)

    def test_tampered_and_reordered_provider_notifications_do_not_call_payfast(self):
        original = _provider_payload()
        variations = []
        for key, changed in (
            ("amount_gross", "1.00"),
            ("merchant_id", "10000101"),
            ("custom_str2", "tampered"),
            ("signature", "0" * 32),
        ):
            payload = original.copy()
            payload[key] = changed
            variations.append(payload)
        payload = original.copy()
        del payload["item_description"]
        variations.append(payload)
        reordered = dict(reversed(list(original.items())))
        variations.append(reordered)
        for payload in variations:
            with self.subTest(keys=list(payload)[:3]):
                valid, request = self.verify(payload)
                self.assertFalse(valid)
                request.assert_not_called()

    def test_checkout_signature_contract_remains_distinct_from_notification_signature(self):
        payload = _provider_payload()
        # Checkout deliberately excludes blank values. ITN validation must not.
        self.assertNotEqual(
            generate_payfast_signature(payload, "synthetic-passphrase"),
            payload["signature"],
        )
