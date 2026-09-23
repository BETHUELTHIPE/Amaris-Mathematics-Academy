import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from content.models import (
    LiveClassBooking,
    StudentRecord,
    TutorAvailabilitySlot,
)
from content.services.live_classes import (
    PaymentSecurityError,
    create_live_class_checkout,
    process_live_class_notification,
)
from content.tasks import (
    deliver_live_class_confirmation,
    deliver_live_class_reminder,
    expire_live_class_holds,
)


class MockPayFastGateway:
    def __init__(self, result=True):
        self.result = result
        self.calls = 0

    def verify_notification(self, payload):
        self.calls += 1
        del payload
        return self.result


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="Amaris Mathematics Academy <noreply@example.test>",
)
class LiveClassBookingTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.tutor = user_model.objects.create_user(
            username="tutor.priya",
            first_name="Priya",
            last_name="Naidoo",
            email="tutor@example.test",
        )
        self.student = StudentRecord.objects.create(
            supabase_user_id=uuid.UUID("00000000-0000-4000-8000-000000000201"),
            email="live.student@example.test",
            first_name="Live",
            last_name="Student",
        )
        self.other_student = StudentRecord.objects.create(
            supabase_user_id=uuid.UUID("00000000-0000-4000-8000-000000000202"),
            email="other.live.student@example.test",
            first_name="Other",
            last_name="Student",
        )
        start = timezone.now() + timedelta(hours=3)
        self.slot = TutorAvailabilitySlot.objects.create(
            tutor=self.tutor,
            programme=TutorAvailabilitySlot.Programme.CAPS,
            subject=TutorAvailabilitySlot.Subject.MATHEMATICS,
            level="Grade 12",
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            zoom_join_url="https://zoom.example.test/j/123456789",
            is_active=True,
        )

    def checkout(self, student=None, key="liveclass-checkout-001"):
        return create_live_class_checkout(
            student=student or self.student,
            slot=self.slot,
            topic="Differential calculus",
            idempotency_key=key,
        )

    def callback(self, booking, **overrides):
        payload = {
            "m_payment_id": booking.reference,
            "pf_payment_id": "PF-LIVE-SANDBOX-001",
            "payment_status": "COMPLETE",
            "amount_gross": "250.00",
            "custom_str1": str(booking.student.supabase_user_id),
            "custom_str2": booking.reference,
            "signature": "synthetic-signature-never-sent",
        }
        payload.update({key: str(value) for key, value in overrides.items()})
        return payload

    def test_public_availability_exposes_tutor_and_time_but_not_zoom_link(self):
        response = self.client.get(
            reverse("live-class-slots"),
            {
                "programme": "caps",
                "subject": "mathematics",
                "level": "Grade 12",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        slot = response.json()[0]
        self.assertEqual(slot["tutor"], "Priya Naidoo")
        self.assertEqual(slot["price"], "250.00")
        self.assertNotIn("zoom_join_url", slot)

    def test_checkout_is_server_priced_at_r250_and_holds_slot(self):
        checkout = self.checkout()
        booking = LiveClassBooking.objects.get(reference=checkout.booking_reference)

        self.assertEqual(booking.amount, Decimal("250.00"))
        self.assertEqual(checkout.fields["amount"], "250.00")
        self.assertIn("sandbox.payfast.co.za", checkout.gateway_url)
        self.assertEqual(booking.status, LiveClassBooking.Status.PENDING_PAYMENT)
        self.assertEqual(booking.slot_id, self.slot.pk)
        self.assertGreater(booking.hold_expires_at, timezone.now())

        with self.assertRaises(PaymentSecurityError):
            self.checkout(
                student=self.other_student,
                key="liveclass-checkout-002",
            )

    def test_tampered_amount_never_confirms_booking(self):
        checkout = self.checkout()
        booking = LiveClassBooking.objects.get(reference=checkout.booking_reference)

        result = process_live_class_notification(
            self.callback(booking, amount_gross="1.00"),
            gateway=MockPayFastGateway(True),
        )

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "tampered_amount")
        booking.refresh_from_db()
        self.assertEqual(booking.status, LiveClassBooking.Status.PENDING_PAYMENT)
        self.assertIsNone(booking.paid_at)
        self.assertIsNone(booking.invoice_number)

    def test_verified_payment_confirms_booking_and_creates_invoice_number(self):
        checkout = self.checkout()
        booking = LiveClassBooking.objects.get(reference=checkout.booking_reference)

        result = process_live_class_notification(
            self.callback(booking),
            gateway=MockPayFastGateway(True),
        )

        self.assertTrue(result.accepted)
        booking.refresh_from_db()
        self.assertEqual(booking.status, LiveClassBooking.Status.CONFIRMED)
        self.assertIsNotNone(booking.paid_at)
        self.assertIsNotNone(booking.gateway_verified_at)
        self.assertTrue(booking.invoice_number.startswith("INV-LIVE-"))

    def test_confirmation_email_contains_zoom_details_and_invoice_attachment(self):
        checkout = self.checkout()
        booking = LiveClassBooking.objects.get(reference=checkout.booking_reference)
        process_live_class_notification(
            self.callback(booking),
            gateway=MockPayFastGateway(True),
        )

        delivered = deliver_live_class_confirmation.run()

        self.assertEqual(delivered, 1)
        booking.refresh_from_db()
        self.assertIsNotNone(booking.confirmation_sent_at)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.student.email])
        self.assertIn("confirmed", message.subject.lower())
        self.assertIn(self.slot.zoom_join_url, message.body)
        self.assertIn(booking.invoice_number, message.body)
        self.assertEqual(len(message.attachments), 1)

        self.assertEqual(deliver_live_class_confirmation.run(), 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_reminder_is_sent_once_inside_thirty_minute_window(self):
        checkout = self.checkout()
        booking = LiveClassBooking.objects.get(reference=checkout.booking_reference)
        process_live_class_notification(
            self.callback(booking),
            gateway=MockPayFastGateway(True),
        )
        deliver_live_class_confirmation.run()
        mail.outbox.clear()

        start = timezone.now() + timedelta(minutes=25)
        self.slot.starts_at = start
        self.slot.ends_at = start + timedelta(hours=1)
        self.slot.save(update_fields=("starts_at", "ends_at", "updated_at"))

        delivered = deliver_live_class_reminder.run()

        self.assertEqual(delivered, 1)
        booking.refresh_from_db()
        self.assertIsNotNone(booking.reminder_sent_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("30 minutes", mail.outbox[0].subject)
        self.assertIn(self.slot.zoom_join_url, mail.outbox[0].body)

        self.assertEqual(deliver_live_class_reminder.run(), 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_expired_unpaid_hold_releases_slot(self):
        checkout = self.checkout()
        booking = LiveClassBooking.objects.get(reference=checkout.booking_reference)
        LiveClassBooking.objects.filter(pk=booking.pk).update(
            hold_expires_at=timezone.now() - timedelta(seconds=1)
        )

        self.assertEqual(expire_live_class_holds.run(), 1)
        booking.refresh_from_db()
        self.assertEqual(booking.status, LiveClassBooking.Status.EXPIRED)

        replacement = self.checkout(
            student=self.other_student,
            key="liveclass-checkout-003",
        )
        replacement_booking = LiveClassBooking.objects.get(
            reference=replacement.booking_reference
        )
        self.assertEqual(
            replacement_booking.status,
            LiveClassBooking.Status.PENDING_PAYMENT,
        )
