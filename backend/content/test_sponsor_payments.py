import hashlib
import hmac
import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest import skipUnless
from unittest.mock import Mock, patch

from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from .authentication import SupabaseStudentAuthentication
from .services.payments import PaymentSecurityError, generate_payfast_signature
from .services.sponsor_payments import (
    SponsorGatewayUnavailable,
    _settle,
    create_checkout,
    payment_options,
    process_payfast_sponsor_notification,
    valid_paystack_signature,
    verify_paystack,
)
from .sponsor_admin import SponsorContributionAdmin
from .sponsor_models import SponsorAccount, SponsorContribution

ENV = {
    "SPONSOR_PAYMENTS_ENABLED": "true",
    "SPONSOR_PAYFAST_ENABLED": "true",
    "SPONSOR_PAYSTACK_ENABLED": "true",
    "PAYFAST_MODE": "sandbox",
    "PAYFAST_ENV": "sandbox",
    "PAYSTACK_MODE": "test",
    "PAYSTACK_SECRET_KEY": "sk_test_" + "synthetic-key",
    "PAYSTACK_WEBHOOK_SECRET": "whsec_" + "synthetic-key",
    "PAYSTACK_WEBHOOK_SECRET_PREVIOUS": "",
    "PAYSTACK_ALLOW_LEGACY_WEBHOOK_SIGNATURE": "false",
}


@override_settings(PUBLIC_SITE_URL="https://students.example.test", PUBLIC_API_URL="https://api.example.test")
class SponsorPaymentsTests(TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, ENV)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.sponsor = SponsorAccount.objects.create(
            supabase_user_id=uuid.uuid4(), name="Synthetic Sponsor", is_active=True
        )
        self.other = SponsorAccount.objects.create(supabase_user_id=uuid.uuid4(), name="Other Sponsor", is_active=True)
        self.email = "sponsor@example.test"
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION="Bearer synthetic-test-session")
        self.payload = {
            "id": str(self.sponsor.supabase_user_id),
            "email": self.email,
            "email_confirmed_at": "2026-11-01",
        }
        auth = patch.object(SupabaseStudentAuthentication, "_validate_token", return_value=self.payload)
        auth.start()
        self.addCleanup(auth.stop)
        self.checkout = reverse("sponsor-checkout")
        self.webhook = reverse("sponsor-paystack-webhook")

    def begin(self, provider="payfast", key=None, amount="500.00", sponsor=None):
        return create_checkout(
            sponsor=sponsor or self.sponsor,
            email=self.email,
            provider=provider,
            amount=Decimal(amount),
            idempotency_key=key or uuid.uuid4(),
        )

    def paystack_initializer(self, path, *, payload=None):
        self.assertEqual(path, "/transaction/initialize")
        self.assertEqual(payload["amount"], 50000)
        self.assertEqual(payload["currency"], "ZAR")
        self.assertEqual(payload["email"], self.email)
        self.assertEqual(
            payload["callback_url"], "https://students.example.test/sponsor/payments/" + payload["reference"]
        )
        return {
            "authorization_url": "https://checkout.paystack.com/synthetic-session",
            "reference": payload["reference"],
        }

    def paystack(self):
        with patch("content.services.sponsor_payments._paystack_request", side_effect=self.paystack_initializer):
            result = self.begin("paystack")
        return SponsorContribution.objects.get(reference=result["reference"])

    def verified(self, contribution, **changes):
        return {
            "reference": contribution.reference,
            "status": "success",
            "currency": "ZAR",
            "domain": "test",
            "amount": 50000,
            "id": 123456,
            "customer": {"email": self.email},
            **changes,
        }

    def post_hook(self, event, *, timestamp=None, signature=None):
        raw = json.dumps(event, separators=(",", ":")).encode()
        timestamp = int(time.time()) if timestamp is None else timestamp
        signature = (
            signature
            or hmac.new(
                ENV["PAYSTACK_WEBHOOK_SECRET"].encode(), str(timestamp).encode() + b"." + raw, hashlib.sha512
            ).hexdigest()
        )
        return self.api.post(
            self.webhook,
            raw,
            content_type="application/json",
            secure=True,
            HTTP_PAYSTACK_SIGNATURE=f"t={timestamp},v1=whk_synthetic:{signature}",
        )

    def pf(self, contribution, **changes):
        return {
            "m_payment_id": contribution.reference,
            "payment_status": "COMPLETE",
            "amount_gross": "500.00",
            "pf_payment_id": "700001",
            **changes,
        }

    def test_both_providers_are_selectable_only_when_explicitly_configured(self):
        self.assertTrue(all(option["available"] for option in payment_options()))
        with patch.dict(os.environ, {"SPONSOR_PAYMENTS_ENABLED": "false"}):
            self.assertFalse(any(option["available"] for option in payment_options()))
            self.assertEqual(
                self.api.post(
                    self.checkout,
                    {"amount": "500", "provider": "payfast", "idempotency_key": str(uuid.uuid4())},
                    secure=True,
                ).status_code,
                503,
            )
        self.assertFalse(SponsorContribution.objects.exists())
        with patch.dict(os.environ, {"PAYSTACK_WEBHOOK_SECRET": ""}):
            self.assertFalse(payment_options()[1]["available"])

    def test_payfast_checkout_has_exact_amount_signed_fields_and_fixed_callback(self):
        result = self.begin()
        contribution = SponsorContribution.objects.get(reference=result["reference"])
        self.assertEqual(result["gateway_url"], "https://sandbox.payfast.co.za/eng/process")
        fields = result["fields"]
        self.assertEqual(fields["amount"], "500.00")
        self.assertEqual(fields["email_address"], self.email)
        self.assertEqual(fields["m_payment_id"], contribution.reference)
        self.assertEqual(fields["notify_url"], "https://api.example.test/api/v1/payfast/itn/")
        from .services.payments import _payfast_credentials

        self.assertEqual(fields["signature"], generate_payfast_signature(fields, _payfast_credentials()[2]))
        self.assertEqual(contribution.status, "pending")
        self.assertIsNone(contribution.gateway_verified_at)
        self.assertIsNone(contribution.received_at)

    def test_paystack_initialization_uses_cents_and_idempotent_reference_once(self):
        key = uuid.uuid4()
        with patch(
            "content.services.sponsor_payments._paystack_request", side_effect=self.paystack_initializer
        ) as gateway:
            first = self.begin("paystack", key=key)
            second = self.begin("paystack", key=key)
        self.assertEqual(first, second)
        gateway.assert_called_once()
        self.assertEqual(SponsorContribution.objects.count(), 1)
        self.assertEqual(first["mode"], "test")
        self.assertEqual(first["fields"], {})

    def test_checkout_rejects_altered_amount_or_provider_for_same_intent(self):
        key = uuid.uuid4()
        self.begin(key=key)
        for changes in ({"amount": "250.00"}, {"provider": "paystack"}):
            with self.assertRaises(PaymentSecurityError):
                self.begin(key=key, **changes)
        self.assertEqual(SponsorContribution.objects.count(), 1)
        second = self.begin(key=key, sponsor=self.other)
        self.assertNotEqual(second["reference"], SponsorContribution.objects.get(sponsor=self.sponsor).reference)

    def test_invalid_amounts_and_user_selected_currency_or_callback_cannot_change_server_facts(self):
        for amount in ("-1", "0", "9.99", "1000000.01", "12.001", "NaN"):
            self.assertEqual(
                self.api.post(
                    self.checkout,
                    {"amount": amount, "provider": "payfast", "idempotency_key": str(uuid.uuid4())},
                    secure=True,
                ).status_code,
                400,
            )
        response = self.api.post(
            self.checkout,
            {
                "amount": "500.00",
                "provider": "payfast",
                "idempotency_key": str(uuid.uuid4()),
                "email": "attacker@example.test",
                "currency": "NGN",
                "return_url": "https://evil.example",
            },
            secure=True,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["currency"], "ZAR")
        self.assertEqual(response.data["fields"]["email_address"], self.email)
        self.assertNotIn("evil.example", str(response.data))

    def test_remote_initialization_uncertainty_keeps_reference_and_does_not_initialize_twice(self):
        key = uuid.uuid4()
        with patch(
            "content.services.sponsor_payments._paystack_request",
            side_effect=SponsorGatewayUnavailable("synthetic outage"),
        ) as gateway:
            for _ in range(2):
                with self.assertRaises(SponsorGatewayUnavailable):
                    self.begin("paystack", key=key)
            gateway.assert_called_once()
        contribution = SponsorContribution.objects.get()
        self.assertEqual(contribution.status, "pending")
        self.assertEqual(contribution.last_error_code, "initialization_review")

    def test_paystack_unsafe_url_and_reference_mismatch_are_rejected(self):
        for url in (
            "https://checkout.paystack.com.evil.example/x",
            "http://checkout.paystack.com/x",
            "https://checkout.paystack.com:444/x",
            "https://user@checkout.paystack.com/x",
        ):
            with patch(
                "content.services.sponsor_payments._paystack_request",
                side_effect=lambda path, payload, url=url: {
                    "reference": payload["reference"],
                    "authorization_url": url,
                },
            ):
                with self.assertRaises(PaymentSecurityError):
                    self.begin("paystack")

    def test_payment_status_is_owner_scoped_and_cancel_return_does_not_mark_paid(self):
        result = self.begin()
        url = reverse("sponsor-payment-status", args=[result["reference"]])
        response = self.api.get(url, {"cancelled": "1", "status": "success"}, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "pending")
        self.assertIsNotNone(response.data["checkout"])
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.payload["id"] = str(self.other.supabase_user_id)
        self.assertEqual(self.api.get(url, secure=True).status_code, 404)
        with patch("content.services.sponsor_payments._paystack_request") as gateway:
            self.assertEqual(
                self.api.post(reverse("sponsor-payment-verify", args=[result["reference"]]), secure=True).status_code,
                404,
            )
            gateway.assert_not_called()

    def test_payfast_verified_completion_is_idempotent_and_failure_does_not_reverse_it(self):
        contribution = SponsorContribution.objects.get(reference=self.begin()["reference"])
        gateway = Mock()
        gateway.verify_notification.return_value = True
        self.assertTrue(process_payfast_sponsor_notification(self.pf(contribution), gateway=gateway).accepted)
        contribution.refresh_from_db()
        received_at = contribution.received_at
        self.assertTrue(process_payfast_sponsor_notification(self.pf(contribution), gateway=gateway).accepted)
        self.assertTrue(
            process_payfast_sponsor_notification(
                self.pf(contribution, payment_status="FAILED"), gateway=gateway
            ).accepted
        )
        contribution.refresh_from_db()
        self.assertEqual(contribution.status, "received")
        self.assertEqual(contribution.received_at, received_at)
        self.assertEqual(contribution.provider_reference, "700001")

    def test_payfast_itn_dispatches_sponsor_reference_after_network_and_gateway_checks(self):
        contribution = SponsorContribution.objects.get(reference=self.begin()["reference"])
        with patch("content.services.payments.HttpPayFastVerificationGateway.verify_notification", return_value=True):
            response = self.api.post(
                reverse("payfast-itn"), self.pf(contribution), secure=True, REMOTE_ADDR="197.97.145.145"
            )
        self.assertEqual(response.status_code, 200)
        contribution.refresh_from_db()
        self.assertEqual(contribution.status, "received")

    def test_payfast_invalid_verification_amount_provider_or_replayed_transaction_is_rejected(self):
        contribution = SponsorContribution.objects.get(reference=self.begin()["reference"])
        gateway = Mock()
        gateway.verify_notification.return_value = False
        self.assertFalse(process_payfast_sponsor_notification(self.pf(contribution), gateway=gateway).accepted)
        gateway.verify_notification.return_value = True
        self.assertFalse(
            process_payfast_sponsor_notification(self.pf(contribution, amount_gross="499.99"), gateway=gateway).accepted
        )
        self.assertTrue(process_payfast_sponsor_notification(self.pf(contribution), gateway=gateway).accepted)
        other = SponsorContribution.objects.get(reference=self.begin()["reference"])
        self.assertFalse(process_payfast_sponsor_notification(self.pf(other), gateway=gateway).accepted)
        other.refresh_from_db()
        self.assertEqual(other.status, "pending")

    def test_paystack_signed_webhook_verifies_via_api_before_credit_and_repeats_are_safe(self):
        contribution = self.paystack()
        event = {"event": "charge.success", "data": {"reference": contribution.reference, "amount": 1}}
        with patch(
            "content.services.sponsor_payments._paystack_request", return_value=self.verified(contribution)
        ) as gateway:
            self.assertEqual(self.post_hook(event).status_code, 200)
            contribution.refresh_from_db()
            first = contribution.received_at
            self.assertEqual(self.post_hook(event).status_code, 200)
        self.assertEqual(gateway.call_count, 2)
        contribution.refresh_from_db()
        self.assertEqual(contribution.received_at, first)
        self.assertEqual(contribution.status, "received")

    def test_paystack_missing_invalid_and_stale_signatures_cannot_trigger_verification(self):
        event = {"event": "charge.success", "data": {"reference": "SC-" + "0" * 32}}
        with patch("content.services.sponsor_payments._paystack_request") as gateway:
            self.assertEqual(self.api.post(self.webhook, event, format="json", secure=True).status_code, 401)
            self.assertEqual(self.post_hook(event, signature="0" * 128).status_code, 401)
            self.assertEqual(self.post_hook(event, timestamp=int(time.time()) - 301).status_code, 401)
            self.assertEqual(self.post_hook(event, timestamp=int(time.time()) + 301).status_code, 401)
            gateway.assert_not_called()
        self.assertFalse(
            valid_paystack_signature(b"{}", {"Paystack-Signature": "t=" + "9" * 500 + ",v1=whk_x:" + "0" * 128})
        )

    def test_modern_webhook_header_cannot_downgrade_to_legacy_signature(self):
        raw = b"{}"
        legacy = hmac.new(ENV["PAYSTACK_SECRET_KEY"].encode(), raw, hashlib.sha512).hexdigest()
        with patch.dict(os.environ, {"PAYSTACK_ALLOW_LEGACY_WEBHOOK_SIGNATURE": "true"}):
            self.assertFalse(valid_paystack_signature(raw, {"X-Paystack-Signature": legacy}))
            self.assertFalse(
                valid_paystack_signature(raw, {"Paystack-Signature": "invalid", "X-Paystack-Signature": legacy})
            )
            with patch.dict(os.environ, {"PAYSTACK_WEBHOOK_SECRET": ""}):
                self.assertTrue(valid_paystack_signature(raw, {"X-Paystack-Signature": legacy}))
                self.assertFalse(
                    valid_paystack_signature(raw, {"Paystack-Signature": "invalid", "X-Paystack-Signature": legacy})
                )

    def test_paystack_wrong_amount_currency_domain_reference_or_payer_never_credits(self):
        contribution = self.paystack()
        for changes in (
            {"amount": 49999},
            {"amount": True},
            {"amount": "50000"},
            {"currency": "NGN"},
            {"domain": "live"},
            {"reference": "SC-wrong"},
            {"customer": {"email": "other@example.test"}},
            {"status": "pending"},
            {"id": "not-an-id"},
        ):
            with (
                self.subTest(changes=changes),
                patch(
                    "content.services.sponsor_payments._paystack_request",
                    return_value=self.verified(contribution, **changes),
                ),
            ):
                with self.assertRaises(PaymentSecurityError):
                    verify_paystack(contribution.reference)
        contribution.refresh_from_db()
        self.assertEqual(contribution.status, "pending")
        self.assertIsNone(contribution.received_at)

    def test_paystack_transient_verification_failure_returns_retryable_response(self):
        contribution = self.paystack()
        with patch(
            "content.services.sponsor_payments._paystack_request",
            side_effect=SponsorGatewayUnavailable("synthetic outage"),
        ):
            self.assertEqual(
                self.post_hook({"event": "charge.success", "data": {"reference": contribution.reference}}).status_code,
                503,
            )
        contribution.refresh_from_db()
        self.assertEqual(contribution.status, "pending")

    def test_pausing_new_checkouts_does_not_drop_payment_callbacks(self):
        contribution = self.paystack()
        with (
            patch.dict(os.environ, {"SPONSOR_PAYMENTS_ENABLED": "false"}),
            patch("content.services.sponsor_payments._paystack_request", return_value=self.verified(contribution)),
        ):
            self.assertEqual(
                self.post_hook({"event": "charge.success", "data": {"reference": contribution.reference}}).status_code,
                200,
            )

    def test_test_receipts_are_labelled_and_excluded_from_funding_totals(self):
        contribution = self.paystack()
        with patch("content.services.sponsor_payments._paystack_request", return_value=self.verified(contribution)):
            verify_paystack(contribution.reference)
        response = self.api.get(reverse("sponsor-dashboard"), secure=True)
        self.assertEqual(response.data["summary"]["received"], "0.00")
        self.assertEqual(response.data["summary"]["current_year_received"], "0.00")
        self.assertEqual(response.data["contributions"][0]["payment_mode"], "test")
        self.assertEqual(response.data["contributions"][0]["provider"], "paystack")
        self.assertEqual([item["provider"] for item in response.data["payment_options"]], ["payfast", "paystack"])
        self.assertIn("test", self.api.get(reverse("sponsor-statement"), secure=True).content.decode())

    def test_live_mode_requires_live_credentials_and_test_verification_cannot_cross_modes(self):
        contribution = self.paystack()
        with patch.dict(os.environ, {"PAYSTACK_MODE": "live"}):
            self.assertFalse(payment_options()[1]["available"])
            with self.assertRaises(PaymentSecurityError):
                verify_paystack(contribution.reference)

    def test_verified_live_receipt_updates_actual_funding_totals(self):
        with patch.dict(os.environ, {"PAYSTACK_MODE": "live", "PAYSTACK_SECRET_KEY": "sk_live_" + "synthetic-key"}):
            contribution = self.paystack()
            with patch(
                "content.services.sponsor_payments._paystack_request",
                return_value=self.verified(contribution, domain="live"),
            ):
                verify_paystack(contribution.reference)
        response = self.api.get(reverse("sponsor-dashboard"), secure=True)
        self.assertEqual(response.data["summary"]["received"], "500.00")
        self.assertEqual(response.data["summary"]["current_year_received"], "500.00")

    def test_empty_payfast_credentials_do_not_offer_broken_checkout(self):
        with patch.dict(os.environ, {"PAYFAST_MERCHANT_ID": "", "PAYFAST_MERCHANT_KEY": ""}):
            self.assertFalse(payment_options()[0]["available"])

    def test_webhook_rotation_multiple_signatures_and_body_tampering(self):
        raw = b"{}"
        timestamp = str(int(time.time()))
        old_secret = "whsec_" + "previous-synthetic-key"
        signature = hmac.new(old_secret.encode(), timestamp.encode() + b"." + raw, hashlib.sha512).hexdigest()
        headers = {"Paystack-Signature": f"t={timestamp},v1=whk_new:{'0' * 128},v1=whk_old:{signature}"}
        with patch.dict(os.environ, {"PAYSTACK_WEBHOOK_SECRET_PREVIOUS": old_secret}):
            self.assertTrue(valid_paystack_signature(raw, headers))
            self.assertFalse(valid_paystack_signature(b"{ }", headers))
        self.assertFalse(valid_paystack_signature(raw, headers))

    def test_admin_retains_gateway_records_and_only_allows_deleting_unreceived_manual_pledges(self):
        from django.contrib import admin

        request = RequestFactory().get("/admin/")
        request.user = Mock()
        request.user.has_perm.return_value = True
        model_admin = SponsorContributionAdmin(SponsorContribution, admin.site)
        contribution = SponsorContribution.objects.get(reference=self.begin()["reference"])
        self.assertFalse(model_admin.has_delete_permission(request, contribution))
        self.assertFalse(model_admin.has_delete_permission(request))
        manual = SponsorContribution.objects.create(sponsor=self.sponsor, reference="manual-pledge", amount="100")
        self.assertTrue(model_admin.has_delete_permission(request, manual))

    def test_gateway_receipts_cannot_be_marked_received_without_verification(self):
        contribution = SponsorContribution.objects.get(reference=self.begin()["reference"])
        with self.assertRaises(IntegrityError), transaction.atomic():
            SponsorContribution.objects.filter(pk=contribution.pk).update(
                status="received", received_at=contribution.created_at
            )


@skipUnless(connection.vendor == "postgresql", "Financial row-lock test requires PostgreSQL")
class SponsorSettlementConcurrencyTests(TransactionTestCase):
    def test_duplicate_parallel_settlements_only_record_one_received_contribution(self):
        sponsor = SponsorAccount.objects.create(supabase_user_id=uuid.uuid4(), name="Test", is_active=True)
        contribution = SponsorContribution.objects.create(
            sponsor=sponsor,
            reference="SC-concurrency",
            amount="500",
            provider="paystack",
            payment_mode="test",
            payment_email="sponsor@example.test",
            status="pending",
        )

        def settle():
            close_old_connections()
            try:
                return _settle(
                    contribution.reference, "paystack", "test", "900001", Decimal("500"), "sponsor@example.test"
                )
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(lambda _: settle(), range(2))), ["received", "received"])
        self.assertEqual(SponsorContribution.objects.filter(status="received").count(), 1)
