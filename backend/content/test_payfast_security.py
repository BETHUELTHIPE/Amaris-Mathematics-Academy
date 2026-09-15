from __future__ import annotations

import uuid
from decimal import Decimal

from django.test import TestCase

from content.models import Course, CourseCategory, Enrollment, Payment, StudentRecord
from content.payment_models import Invoice, NotificationOutbox, ServiceTicket
from content.services.payfast_security import (
    PAYFAST_SANDBOX_PROCESS_URL,
    PayFastSandboxConfig,
    PayFastSandboxVerifier,
    build_sandbox_checkout_fields,
    generate_payfast_signature,
)
from content.services.payments import create_checkout, process_payfast_notification


class MockValidDataChecker:
    """Deterministic server-validation stand-in; it never performs network I/O."""

    def __init__(self, outcome=True):
        self.outcome = outcome
        self.calls = 0

    def __call__(self, payload):
        self.calls += 1
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return bool(self.outcome)


class PayFastSandboxSecurityTests(TestCase):
    merchant_id = "99990001"
    passphrase = "synthetic-sandbox-passphrase"
    source_ip = "198.51.100.42"
    allowed_sources = ("198.51.100.0/24",)

    def setUp(self):
        self.student = StudentRecord.objects.create(
            supabase_user_id=uuid.UUID("00000000-0000-4000-8000-000000000201"),
            email="sandbox.payment@example.test",
            first_name="Sandbox",
            last_name="Student",
        )
        category = CourseCategory.objects.create(
            name="Sandbox Payment Tests",
            slug="sandbox-payment-tests",
        )
        self.course = Course.objects.create(
            category=category,
            title="Synthetic Sandbox Mathematics",
            slug="synthetic-sandbox-mathematics",
            short_description="Synthetic sandbox payment fixture",
            description="No real payment or student information is used.",
            curriculum="Synthetic",
            academic_level="Test",
            price=Decimal("950.00"),
            status=Course.Status.PUBLISHED,
        )
        self.checkout = create_checkout(
            student=self.student,
            course=self.course,
            idempotency_key="sandbox-security-001",
        )

    def sandbox_config(self):
        return PayFastSandboxConfig(
            merchant_id=self.merchant_id,
            merchant_key="synthetic-merchant-key",
            passphrase=self.passphrase,
            return_url="https://example.test/payments/return",
            cancel_url="https://example.test/payments/cancelled",
            notify_url="https://example.test/api/v1/payments/payfast/notify",
        )

    def signed_callback(self, **overrides):
        payload = {
            "merchant_id": self.merchant_id,
            "m_payment_id": self.checkout.payment_reference,
            "pf_payment_id": "PF-SANDBOX-SECURITY-001",
            "payment_status": "COMPLETE",
            "amount_gross": "950.00",
            "custom_str1": str(self.student.supabase_user_id),
            "custom_str2": self.course.slug,
        }
        payload.update({key: str(value) for key, value in overrides.items()})
        payload["signature"] = generate_payfast_signature(
            payload,
            passphrase=self.passphrase,
        )
        return payload

    def verifier(self, checker=None, *, source_ip=None):
        return PayFastSandboxVerifier(
            merchant_id=self.merchant_id,
            passphrase=self.passphrase,
            source_ip=source_ip or self.source_ip,
            allowed_sources=self.allowed_sources,
            valid_data_checker=checker or MockValidDataChecker(True),
        )

    def assert_no_fulfilment(self):
        self.assertEqual(Enrollment.objects.count(), 0)
        self.assertEqual(Invoice.objects.count(), 0)
        self.assertEqual(ServiceTicket.objects.count(), 0)
        self.assertEqual(NotificationOutbox.objects.count(), 0)

    def test_checkout_is_signed_for_sandbox_without_live_money(self):
        fields = build_sandbox_checkout_fields(
            self.checkout.fields,
            config=self.sandbox_config(),
        )
        self.assertEqual(PAYFAST_SANDBOX_PROCESS_URL, self.checkout.gateway_url)
        self.assertEqual(fields["amount"], "950.00")
        self.assertEqual(fields["m_payment_id"], self.checkout.payment_reference)
        self.assertEqual(fields["merchant_id"], self.merchant_id)
        self.assertNotIn("passphrase", fields)
        self.assertEqual(
            fields["signature"],
            generate_payfast_signature(fields, passphrase=self.passphrase),
        )
        self.assertEqual(Payment.objects.get().status, Payment.Status.PENDING)
        self.assert_no_fulfilment()

    def test_signed_sandbox_callback_is_server_verified_before_fulfilment(self):
        checker = MockValidDataChecker(True)
        result = process_payfast_notification(
            self.signed_callback(),
            gateway=self.verifier(checker),
        )
        self.assertTrue(result.accepted)
        self.assertEqual(checker.calls, 1)
        payment = Payment.objects.get()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertIsNotNone(payment.gateway_verified_at)
        self.assertEqual(Enrollment.objects.count(), 1)
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(ServiceTicket.objects.count(), 1)
        self.assertEqual(NotificationOutbox.objects.count(), 1)

    def test_invalid_signature_is_rejected_before_valid_data_check(self):
        checker = MockValidDataChecker(True)
        payload = self.signed_callback()
        payload["signature"] = "0" * 32
        result = process_payfast_notification(
            payload,
            gateway=self.verifier(checker),
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "invalid_callback")
        self.assertEqual(checker.calls, 0)
        self.assertEqual(Payment.objects.get().status, Payment.Status.PENDING)
        self.assert_no_fulfilment()

    def test_wrong_merchant_is_rejected_even_with_matching_attacker_signature(self):
        checker = MockValidDataChecker(True)
        payload = self.signed_callback(merchant_id="99990002")
        result = process_payfast_notification(
            payload,
            gateway=self.verifier(checker),
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "invalid_callback")
        self.assertEqual(checker.calls, 0)
        self.assert_no_fulfilment()

    def test_callback_from_unapproved_source_is_rejected(self):
        checker = MockValidDataChecker(True)
        result = process_payfast_notification(
            self.signed_callback(),
            gateway=self.verifier(checker, source_ip="203.0.113.9"),
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "invalid_callback")
        self.assertEqual(checker.calls, 0)
        self.assert_no_fulfilment()

    def test_signed_but_tampered_amount_is_rejected_by_backend_order_amount(self):
        payload = self.signed_callback(amount_gross="1.00")
        result = process_payfast_notification(
            payload,
            gateway=self.verifier(),
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "tampered_amount")
        self.assertEqual(Payment.objects.get().status, Payment.Status.PENDING)
        self.assert_no_fulfilment()

    def test_server_validation_timeout_is_retryable_and_grants_nothing(self):
        checker = MockValidDataChecker(TimeoutError("synthetic validation timeout"))
        result = process_payfast_notification(
            self.signed_callback(),
            gateway=self.verifier(checker),
        )
        self.assertFalse(result.accepted)
        self.assertTrue(result.retryable)
        self.assertEqual(result.reason, "verification_timeout")
        self.assertEqual(Payment.objects.get().status, Payment.Status.PENDING)
        self.assert_no_fulfilment()

    def test_server_validation_network_failure_is_retryable_and_grants_nothing(self):
        checker = MockValidDataChecker(ConnectionError("synthetic network failure"))
        result = process_payfast_notification(
            self.signed_callback(),
            gateway=self.verifier(checker),
        )
        self.assertFalse(result.accepted)
        self.assertTrue(result.retryable)
        self.assertEqual(result.reason, "verification_network_failure")
        self.assertEqual(Payment.objects.get().status, Payment.Status.PENDING)
        self.assert_no_fulfilment()
