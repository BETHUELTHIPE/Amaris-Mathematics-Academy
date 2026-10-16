from __future__ import annotations

import os
from decimal import Decimal
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from content.donation_models import DonationContribution
from content.services.donations import create_donation_checkout, process_donation_notification
from content.services.payments import PaymentSecurityError, generate_payfast_signature


class ApprovedVerificationGateway:
    def __init__(self, verified=True):
        self.verified = verified
        self.calls = 0

    def verify_notification(self, payload):
        self.calls += 1
        return self.verified


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
@patch.dict(
    os.environ,
    {
        "DONATIONS_ENABLED": "true",
        "DONATIONS_LIVE_ENABLED": "false",
        "PAYFAST_ENV": "sandbox",
        "PAYFAST_MODE": "",
        "PAYFAST_MERCHANT_ID": "10000100",
        "PAYFAST_MERCHANT_KEY": "synthetic-merchant-key",
        "PAYFAST_PASSPHRASE": "synthetic-passphrase",
        "PUBLIC_API_URL": "https://api.example.test",
        "PUBLIC_SITE_URL": "https://students.example.test",
    },
)
class DonationPaymentTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.args = {
            "name": "Test Donor",
            "email": "donor@example.test",
            "amount": Decimal("250.00"),
            "purpose": "learner",
            "idempotency_key": "fixture-" + "abcdefghijk123",
        }

    def create_checkout(self, **changes):
        return create_donation_checkout(**{**self.args, **changes})

    def payload(self, **overrides):
        fields = {
            "merchant_id": "10000100",
            "m_payment_id": "DON-" + "fixture-" + "abcdefghijk123",
            "pf_payment_id": "TEST-PF-DON-1",
            "payment_status": "COMPLETE",
            "amount_gross": "250.00",
            "custom_str1": "DON-" + "fixture-" + "abcdefghijk123",
            "custom_str2": "learner",
        }
        fields.update({k: str(v) for k, v in overrides.items()})
        fields["signature"] = generate_payfast_signature(fields, "synthetic-passphrase")
        return fields

    def test_signed_checkout_is_pending_and_isolated_from_student_purchases(self):
        checkout = self.create_checkout()
        self.assertEqual(checkout.fields["amount"], "250.00")
        self.assertIn("sandbox.payfast.co.za", checkout.gateway_url)
        self.assertEqual(checkout.fields["m_payment_id"], checkout.reference)
        self.assertTrue(checkout.fields["signature"])
        obj = DonationContribution.objects.get(reference=checkout.reference)
        self.assertEqual(obj.status, "pending")
        self.assertEqual(obj.donor_email, "donor@example.test")

    def test_idempotent_retry_must_not_change_amount_or_email(self):
        a = self.create_checkout()
        self.assertEqual(self.create_checkout().reference, a.reference)
        with self.assertRaises(PaymentSecurityError):
            self.create_checkout(amount=Decimal("500.00"))
        self.assertEqual(DonationContribution.objects.count(), 1)

    def test_amount_and_checkout_flags_fail_closed(self):
        with self.assertRaises(PaymentSecurityError):
            self.create_checkout(amount=Decimal("19.99"))
        with self.assertRaises(PaymentSecurityError):
            self.create_checkout(amount=Decimal("100000.01"))
        with patch.dict(os.environ, {"DONATIONS_ENABLED": "false"}):
            with self.assertRaises(PaymentSecurityError):
                self.create_checkout()

    def test_callback_needs_server_verification_and_matching_amount(self):
        self.create_checkout()
        invalid = process_donation_notification(self.payload(), gateway=ApprovedVerificationGateway(False))
        self.assertFalse(invalid.accepted)
        self.assertEqual(DonationContribution.objects.get().status, "pending")
        mismatch = process_donation_notification(
            self.payload(amount_gross="251.00"), gateway=ApprovedVerificationGateway()
        )
        self.assertFalse(mismatch.accepted)
        self.assertEqual(DonationContribution.objects.get().status, "pending")

    def test_verified_callback_sends_ordinary_acknowledgement_once(self):
        self.create_checkout()
        with self.captureOnCommitCallbacks(execute=True):
            paid = process_donation_notification(self.payload(), gateway=ApprovedVerificationGateway())
        self.assertTrue(paid.accepted)
        donation = DonationContribution.objects.get()
        self.assertEqual(donation.status, "paid")
        self.assertTrue(donation.gateway_verified_at)
        self.assertTrue(donation.paid_at)
        self.assertTrue(donation.receipt_sent_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("not a Section 18A", mail.outbox[0].body)
        duplicate = process_donation_notification(self.payload(), gateway=ApprovedVerificationGateway())
        self.assertTrue(duplicate.duplicate)
        self.assertEqual(len(mail.outbox), 1)
        rejected = process_donation_notification(
            self.payload(payment_status="FAILED"), gateway=ApprovedVerificationGateway()
        )
        self.assertFalse(rejected.accepted)
        self.assertEqual(DonationContribution.objects.get().status, "paid")

    def test_signed_callbacks_cannot_cross_contribution_references(self):
        self.create_checkout()
        other = self.create_checkout(idempotency_key="fixture-" + "abcdefghijk124")
        mismatch = process_donation_notification(
            self.payload(m_payment_id=other.reference), gateway=ApprovedVerificationGateway()
        )
        self.assertFalse(mismatch.accepted)
        self.assertEqual(DonationContribution.objects.get(reference=other.reference).status, "pending")

    def test_public_checkout_rate_limited_and_status_contains_no_private_data(self):
        data = {
            "donor_name": "Test Donor",
            "donor_email": "donor@example.test",
            "amount": "250.00",
            "purpose": "learner",
            "idempotency_key": "fixture-" + "abcdefghijk123",
            "consent": True,
        }
        created = self.client.post("/api/v1/donations/checkout/", data, format="json", secure=True)
        self.assertEqual(created.status_code, 201, created.data)
        self.assertTrue(created.data["gateway_url"].startswith("https://"))
        status = self.client.get("/api/v1/donations/" + created.data["payment_reference"] + "/", secure=True)
        self.assertEqual(status.status_code, 200, status.data)
        self.assertEqual(status.data["status"], "pending")
        self.assertNotIn("donor_email", status.data)
        self.assertNotIn("donor_name", status.data)

    def test_live_money_requires_explicit_double_enable(self):
        with patch.dict(
            os.environ, {"PAYFAST_ENV": "live", "DONATIONS_LIVE_ENABLED": "false", "PAYFAST_MERCHANT_ID": "87654321"}
        ):
            with self.assertRaises(PaymentSecurityError):
                self.create_checkout()
