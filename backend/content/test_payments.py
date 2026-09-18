from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from content.models import Course, CourseCategory, Enrollment, Payment, StudentRecord
from content.payment_models import (
    Invoice,
    NotificationOutbox,
    PaymentWebhookEvent,
    ServiceTicket,
)
from content.tasks import deliver_transactional_email
from content.services.payments import (
    PAYMENT_CANCELLED,
    PaymentSecurityError,
    authoritative_payment_status,
    create_checkout,
    process_payfast_notification,
)


class MockPayFastGateway:
    """Deterministic PayFast verification adapter. It never performs network I/O."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes or (True,))
        self.calls = 0

    def verify_notification(self, payload):
        self.calls += 1
        outcome = self.outcomes.pop(0) if self.outcomes else True
        if isinstance(outcome, BaseException):
            raise outcome
        return bool(outcome)


class PayFastPaymentAuthorityTests(TestCase):
    def setUp(self):
        self.student = StudentRecord.objects.create(
            supabase_user_id=uuid.UUID("00000000-0000-4000-8000-000000000101"),
            email="payment.student@example.test",
            first_name="Synthetic",
            last_name="Student",
        )
        self.other_student = StudentRecord.objects.create(
            supabase_user_id=uuid.UUID("00000000-0000-4000-8000-000000000102"),
            email="other.student@example.test",
            first_name="Other",
            last_name="Student",
        )
        category = CourseCategory.objects.create(name="Payment Tests", slug="payment-tests")
        self.course = Course.objects.create(
            category=category,
            title="Synthetic Calculus Course",
            slug="synthetic-calculus-course",
            short_description="Synthetic payment fixture",
            description="No real student or payment data is used.",
            curriculum="Synthetic",
            academic_level="Test",
            price=Decimal("950.00"),
            status=Course.Status.PUBLISHED,
        )
        self.other_course = Course.objects.create(
            category=category,
            title="Synthetic Algebra Course",
            slug="synthetic-algebra-course",
            short_description="Synthetic payment fixture",
            description="No real student or payment data is used.",
            curriculum="Synthetic",
            academic_level="Test",
            price=Decimal("450.00"),
            status=Course.Status.PUBLISHED,
        )
        self.checkout = create_checkout(
            student=self.student,
            course=self.course,
            idempotency_key="checkout-payment-001",
        )

    def callback(self, **overrides):
        payload = {
            "m_payment_id": self.checkout.payment_reference,
            "pf_payment_id": "PF-SANDBOX-TRANSACTION-001",
            "payment_status": "COMPLETE",
            "amount_gross": "950.00",
            "custom_str1": str(self.student.supabase_user_id),
            "custom_str2": self.course.slug,
            "signature": "synthetic-signature-never-sent",
        }
        payload.update({key: str(value) for key, value in overrides.items()})
        return payload

    def assert_no_fulfilment(self):
        self.assertEqual(Enrollment.objects.count(), 0)
        self.assertEqual(Invoice.objects.count(), 0)
        self.assertEqual(ServiceTicket.objects.count(), 0)
        self.assertEqual(NotificationOutbox.objects.count(), 0)

    def test_checkout_creation_is_pending_server_priced_and_does_not_grant_access(self):
        payment = Payment.objects.get(reference=self.checkout.payment_reference)
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.amount, self.course.price)
        self.assertEqual(self.checkout.fields["amount"], "950.00")
        self.assertIn("sandbox.payfast.co.za", self.checkout.gateway_url)
        self.assertEqual(self.checkout.fields["custom_str1"], str(self.student.supabase_user_id))
        self.assertEqual(self.checkout.fields["custom_str2"], self.course.slug)
        self.assert_no_fulfilment()

    def test_checkout_idempotency_reuses_payment_and_rejects_changed_purchase(self):
        again = create_checkout(
            student=self.student,
            course=self.course,
            idempotency_key="checkout-payment-001",
        )
        self.assertEqual(again.payment_reference, self.checkout.payment_reference)
        self.assertEqual(Payment.objects.count(), 1)

        with self.assertRaises(PaymentSecurityError):
            create_checkout(
                student=self.other_student,
                course=self.course,
                idempotency_key="checkout-payment-001",
            )
        self.assertEqual(Payment.objects.count(), 1)

    def test_pending_callback_stays_pending_without_fulfilment(self):
        result = process_payfast_notification(
            self.callback(payment_status="PENDING"),
            gateway=MockPayFastGateway(True),
        )
        self.assertTrue(result.accepted)
        payment = Payment.objects.get(reference=self.checkout.payment_reference)
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertIsNotNone(payment.gateway_verified_at)
        self.assert_no_fulfilment()

    def test_successful_verified_callback_atomically_activates_service_and_creates_artifacts(
        self,
    ):
        result = process_payfast_notification(self.callback(), gateway=MockPayFastGateway(True))
        self.assertTrue(result.accepted)

        payment = Payment.objects.get(reference=self.checkout.payment_reference)
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertIsNotNone(payment.gateway_verified_at)
        self.assertEqual(payment.verification_source, "payfast_server_verification")
        self.assertEqual(payment.provider_reference, "PF-SANDBOX-TRANSACTION-001")

        enrollment = Enrollment.objects.get(student=self.student, course=self.course)
        self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)
        self.assertEqual(payment.enrollment_id, enrollment.pk)

        invoice = Invoice.objects.get(payment=payment)
        ticket = ServiceTicket.objects.get(payment=payment)
        outbox = NotificationOutbox.objects.get(payment=payment)
        self.assertEqual(invoice.amount, payment.amount)
        self.assertEqual(invoice.student_id, self.student.pk)
        self.assertEqual(ticket.enrollment_id, enrollment.pk)
        self.assertEqual(outbox.status, NotificationOutbox.Status.QUEUED)
        self.assertEqual(outbox.destination, self.student.email)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="Amaris <noreply@example.test>",
    )
    def test_verified_payment_notification_is_delivered_once_from_outbox(self):
        process_payfast_notification(self.callback(), gateway=MockPayFastGateway(True))
        outbox = NotificationOutbox.objects.get()
        self.assertEqual(outbox.status, NotificationOutbox.Status.QUEUED)

        delivered = deliver_transactional_email.run()
        self.assertEqual(delivered, 1)
        outbox.refresh_from_db()
        self.assertEqual(outbox.status, NotificationOutbox.Status.SENT)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.student.email])
        self.assertIn(self.course.title, mail.outbox[0].subject)

        self.assertEqual(deliver_transactional_email.run(), 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_failed_callback_never_activates_service(self):
        result = process_payfast_notification(
            self.callback(payment_status="FAILED"),
            gateway=MockPayFastGateway(True),
        )
        self.assertTrue(result.accepted)
        payment = Payment.objects.get(reference=self.checkout.payment_reference)
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assert_no_fulfilment()

    def test_cancelled_callback_never_activates_service(self):
        result = process_payfast_notification(
            self.callback(payment_status="CANCELLED"),
            gateway=MockPayFastGateway(True),
        )
        self.assertTrue(result.accepted)
        payment = Payment.objects.get(reference=self.checkout.payment_reference)
        self.assertEqual(payment.status, PAYMENT_CANCELLED)
        self.assert_no_fulfilment()

    def test_delayed_callback_within_replay_window_is_accepted(self):
        payment = Payment.objects.get(reference=self.checkout.payment_reference)
        Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(hours=6))

        result = process_payfast_notification(self.callback(), gateway=MockPayFastGateway(True))

        self.assertTrue(result.accepted)
        self.assertEqual(Payment.objects.get(pk=payment.pk).status, Payment.Status.PAID)
        self.assertEqual(Enrollment.objects.filter(student=self.student, course=self.course).count(), 1)

    def test_callback_outside_replay_window_is_rejected_without_gateway_call(self):
        payment = Payment.objects.get(reference=self.checkout.payment_reference)
        Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(days=8))
        gateway = MockPayFastGateway(True)

        result = process_payfast_notification(self.callback(), gateway=gateway)

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "callback_window_expired")
        self.assertEqual(gateway.calls, 0)
        self.assertEqual(Payment.objects.get(pk=payment.pk).status, Payment.Status.PENDING)
        self.assert_no_fulfilment()

    def test_duplicate_callback_is_idempotent_for_payment_enrollment_invoice_and_ticket(
        self,
    ):
        gateway = MockPayFastGateway(True)
        first = process_payfast_notification(self.callback(), gateway=gateway)
        second = process_payfast_notification(self.callback(), gateway=gateway)

        self.assertTrue(first.accepted)
        self.assertTrue(second.accepted)
        self.assertTrue(second.duplicate)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Enrollment.objects.count(), 1)
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(ServiceTicket.objects.count(), 1)
        self.assertEqual(NotificationOutbox.objects.count(), 1)
        self.assertEqual(PaymentWebhookEvent.objects.count(), 1)
        self.assertEqual(
            gateway.calls,
            1,
            "Processed duplicate callbacks must not re-contact the gateway.",
        )

    def test_invalid_callback_cannot_grant_access(self):
        result = process_payfast_notification(self.callback(), gateway=MockPayFastGateway(False))
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "invalid_callback")
        self.assertEqual(Payment.objects.get().status, Payment.Status.PENDING)
        self.assert_no_fulfilment()

    def test_tampered_amount_is_rejected_even_after_gateway_authentication(self):
        result = process_payfast_notification(
            self.callback(amount_gross="1.00"),
            gateway=MockPayFastGateway(True),
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "tampered_amount")
        self.assertEqual(Payment.objects.get().status, Payment.Status.PENDING)
        self.assert_no_fulfilment()

    def test_wrong_student_is_rejected(self):
        result = process_payfast_notification(
            self.callback(custom_str1=self.other_student.supabase_user_id),
            gateway=MockPayFastGateway(True),
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "wrong_student")
        self.assert_no_fulfilment()

    def test_wrong_service_is_rejected(self):
        result = process_payfast_notification(
            self.callback(custom_str2=self.other_course.slug),
            gateway=MockPayFastGateway(True),
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "wrong_service")
        self.assert_no_fulfilment()

    def test_replayed_processed_webhook_cannot_create_new_objects_or_change_amount(
        self,
    ):
        process_payfast_notification(self.callback(), gateway=MockPayFastGateway(True))
        replay = self.callback(amount_gross="999999.00", signature="different-replay-signature")
        result = process_payfast_notification(replay, gateway=MockPayFastGateway(True))

        self.assertTrue(result.duplicate)
        payment = Payment.objects.get()
        self.assertEqual(payment.amount, self.course.price)
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Enrollment.objects.count(), 1)
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(ServiceTicket.objects.count(), 1)
        self.assertEqual(NotificationOutbox.objects.count(), 1)

    def test_verification_timeout_is_retryable_and_grants_nothing(self):
        result = process_payfast_notification(
            self.callback(),
            gateway=MockPayFastGateway(TimeoutError("synthetic timeout")),
        )
        self.assertFalse(result.accepted)
        self.assertTrue(result.retryable)
        self.assertEqual(result.reason, "verification_timeout")
        self.assertEqual(Payment.objects.get().status, Payment.Status.PENDING)
        self.assert_no_fulfilment()

    def test_retry_after_timeout_can_succeed_exactly_once(self):
        gateway = MockPayFastGateway(TimeoutError("synthetic timeout"), True)
        first = process_payfast_notification(self.callback(), gateway=gateway)
        second = process_payfast_notification(self.callback(), gateway=gateway)

        self.assertTrue(first.retryable)
        self.assertTrue(second.accepted)
        self.assertEqual(Payment.objects.get().status, Payment.Status.PAID)
        event = PaymentWebhookEvent.objects.get()
        self.assertEqual(event.attempts, 2)
        self.assertEqual(Enrollment.objects.count(), 1)
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(ServiceTicket.objects.count(), 1)
        self.assertEqual(NotificationOutbox.objects.count(), 1)

    def test_network_failure_is_retryable_and_grants_nothing(self):
        result = process_payfast_notification(
            self.callback(),
            gateway=MockPayFastGateway(ConnectionError("synthetic network failure")),
        )
        self.assertFalse(result.accepted)
        self.assertTrue(result.retryable)
        self.assertEqual(result.reason, "verification_network_failure")
        self.assertEqual(Payment.objects.get().status, Payment.Status.PENDING)
        self.assert_no_fulfilment()

    def test_browser_success_claim_is_not_authoritative(self):
        browser_claim = {"payment_status": "COMPLETE", "success": True}
        self.assertTrue(browser_claim["success"])
        self.assertEqual(
            authoritative_payment_status(self.checkout.payment_reference),
            Payment.Status.PENDING,
        )
        self.assert_no_fulfilment()

    def test_fulfilment_error_rolls_back_paid_state_and_all_service_artifacts(self):
        with patch(
            "content.services.payments.Invoice.objects.get_or_create",
            side_effect=RuntimeError("synthetic db failure"),
        ):
            with self.assertRaises(RuntimeError):
                process_payfast_notification(self.callback(), gateway=MockPayFastGateway(True))

        payment = Payment.objects.get(reference=self.checkout.payment_reference)
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertIsNone(payment.gateway_verified_at)
        self.assert_no_fulfilment()
