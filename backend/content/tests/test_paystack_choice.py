"""Mocked Paystack verification security tests; no external transactions."""

import hashlib
import hmac
import json
from unittest import mock

from django.test import RequestFactory, SimpleTestCase

from content.paystack_views import paystack_webhook
from content.services.payments import PaymentSecurityError
from content.services.paystack import enabled, initialize, verify_and_settle


class PaystackCheckoutTests(SimpleTestCase):
    @mock.patch.dict("os.environ", {}, clear=True)
    def test_disabled_by_default(self):
        self.assertFalse(enabled())
        with self.assertRaises(PaymentSecurityError):
            initialize(email="test@example.com", amount=10, reference="PS-sample", callback_path="/payments/pending")

    @mock.patch.dict(
        "os.environ",
        {
            "PAYSTACK_ENABLED": "true",
            "PAYSTACK_SECRET_KEY": "sk_test_dummy",
            "PUBLIC_SITE_URL": "https://staging.example.com",
        },
    )
    @mock.patch("content.services.paystack._request")
    def test_amount_is_sent_in_cents_and_reference_matches(self, request):
        request.return_value = {
            "authorization_url": "https://checkout.paystack.com/testtoken",
            "reference": "PS-sample",
        }
        from decimal import Decimal

        url = initialize(
            email="student@example.com",
            amount=Decimal("250.00"),
            reference="PS-sample",
            callback_path="/payments/pending",
        )
        self.assertEqual(url, "https://checkout.paystack.com/testtoken")
        self.assertEqual(request.call_args.kwargs["payload"]["amount"], 25000)
        self.assertEqual(request.call_args.kwargs["payload"]["currency"], "ZAR")

    @mock.patch.dict(
        "os.environ",
        {
            "PAYSTACK_ENABLED": "true",
            "PAYSTACK_SECRET_KEY": "sk_test_dummy",
            "PUBLIC_SITE_URL": "https://staging.example.com",
        },
    )
    @mock.patch("content.services.paystack._request")
    def test_reject_untrusted_checkout_url(self, request):
        from decimal import Decimal

        request.return_value = {"authorization_url": "https://evil.invalid/redirect", "reference": "PS-sample"}
        with self.assertRaises(PaymentSecurityError):
            initialize(
                email="x@example.com", amount=Decimal("1.00"), reference="PS-sample", callback_path="/payments/pending"
            )

    @mock.patch("content.services.paystack._request")
    def test_invalid_verified_amount_does_not_settle_payment(self, request):
        for amount in (None, True, -100, "12.50", 12.5, {}, ""):
            with self.subTest(amount=amount):
                request.return_value = {
                    "reference": "PS-example",
                    "status": "success",
                    "currency": "ZAR",
                    "amount": amount,
                    "id": 123456,
                }
                with self.assertRaises(PaymentSecurityError):
                    verify_and_settle("PS-example")


class PaystackWebhookTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @mock.patch.dict("os.environ", {"PAYSTACK_SECRET_KEY": "sk_test_fake"})
    @mock.patch("content.paystack_views.verify_and_settle")
    def test_signed_event_calls_server_verifier_only(self, verify):
        raw = json.dumps({"event": "charge.success", "data": {"reference": "PS-sample"}}).encode()
        signature = hmac.new(b"sk_test_fake", raw, hashlib.sha512).hexdigest()
        request = self.factory.post(
            "/api/v1/paystack/webhook/",
            data=raw,
            content_type="application/json",
            HTTP_X_PAYSTACK_SIGNATURE=signature,
            secure=True,
        )
        response = paystack_webhook(request)
        self.assertEqual(response.status_code, 200)
        verify.assert_called_once_with("PS-sample")

    @mock.patch.dict("os.environ", {"PAYSTACK_SECRET_KEY": "sk_test_fake"})
    @mock.patch("content.paystack_views.verify_and_settle")
    def test_unsigned_event_never_settles(self, verify):
        request = self.factory.post(
            "/api/v1/paystack/webhook/",
            data=b'{"event":"charge.success"}',
            content_type="application/json",
            secure=True,
        )
        self.assertEqual(paystack_webhook(request).status_code, 403)
        verify.assert_not_called()

    @mock.patch.dict(
        "os.environ",
        {
            "PAYSTACK_SECRET_KEY": "sk_test_fake",
            "PAYSTACK_WEBHOOK_SECRET": "whsec_fake",
        },
    )
    @mock.patch("content.paystack_views.verify_and_settle")
    def test_current_timestamped_webhook_signature(self, verify):
        import time

        raw = json.dumps({"event": "charge.success", "data": {"reference": "PS-sample"}}).encode()
        timestamp = str(int(time.time()))
        signature = hmac.new(b"whsec_fake", timestamp.encode() + b"." + raw, hashlib.sha512).hexdigest()
        header = f"t={timestamp},v1=whk_test:{signature}"
        request = self.factory.post(
            "/api/v1/paystack/webhook/",
            data=raw,
            content_type="application/json",
            HTTP_PAYSTACK_SIGNATURE=header,
            secure=True,
        )
        self.assertEqual(paystack_webhook(request).status_code, 200)
        verify.assert_called_once_with("PS-sample")

    @mock.patch.dict("os.environ", {"PAYSTACK_WEBHOOK_SECRET": "whsec_fake"})
    @mock.patch("content.paystack_views.verify_and_settle")
    def test_expired_webhook_signature_rejected(self, verify):
        import time

        raw = json.dumps({"event": "charge.success", "data": {"reference": "PS-sample"}}).encode()
        timestamp = str(int(time.time()) - 1200)
        signature = hmac.new(b"whsec_fake", timestamp.encode() + b"." + raw, hashlib.sha512).hexdigest()
        request = self.factory.post(
            "/api/v1/paystack/webhook/",
            data=raw,
            content_type="application/json",
            HTTP_PAYSTACK_SIGNATURE=f"t={timestamp},v1=whk_test:{signature}",
            secure=True,
        )
        self.assertEqual(paystack_webhook(request).status_code, 403)
        verify.assert_not_called()
