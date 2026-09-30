import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from content.authentication import SupabaseStudentPrincipal
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
            secure=True,
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

    def test_published_slot_id_can_be_used_at_authenticated_checkout(self):
        slot_response = self.client.get(reverse("live-class-slots"), secure=True)
        slot_id = slot_response.json()[0]["id"]
        self.assertEqual(slot_id, self.slot.pk)
        client = APIClient()
        client.force_authenticate(user=SupabaseStudentPrincipal(
            student=self.student,
            supabase_user_id=str(self.student.supabase_user_id),
            email=self.student.email,
        ))
        response = client.post(
            reverse("live-class-checkout"),
            {"slot_id": slot_id, "topic": "Differential calculus", "idempotency_key": "api-liveclass-001"},
            format="json",
            secure=True,
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["fields"]["amount"], "250.00")
        self.assertEqual(response.data["booking"]["tutor"], "Priya Naidoo")

    def test_expired_attempt_cannot_reuse_original_payment_reference(self):
        checkout = self.checkout()
        booking = LiveClassBooking.objects.get(reference=checkout.booking_reference)
        LiveClassBooking.objects.filter(pk=booking.pk).update(hold_expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(PaymentSecurityError):
            self.checkout()
        replacement = self.checkout(key="liveclass-new-attempt-001")
        self.assertNotEqual(replacement.booking_reference, booking.reference)

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

    def test_verified_late_payment_is_visible_for_manual_resolution_without_double_booking(self):
        checkout = self.checkout()
        booking = LiveClassBooking.objects.get(reference=checkout.booking_reference)
        LiveClassBooking.objects.filter(pk=booking.pk).update(hold_expires_at=timezone.now() - timedelta(seconds=1))
        replacement = self.checkout(student=self.other_student, key="replacement-liveclass-001")

        gateway = MockPayFastGateway(True)
        result = process_live_class_notification(self.callback(booking), gateway=gateway)
        self.assertTrue(result.accepted)
        self.assertEqual(result.payment_status, "payment_review")
        booking.refresh_from_db()
        self.assertIsNotNone(booking.paid_at)
        self.assertIsNotNone(booking.gateway_verified_at)
        self.assertIsNone(booking.invoice_number)
        self.assertEqual(booking.status, LiveClassBooking.Status.PAYMENT_REVIEW)
        self.assertEqual(deliver_live_class_confirmation.run(), 0)
        self.assertEqual(len(mail.outbox), 0)
        replacement_booking = LiveClassBooking.objects.get(reference=replacement.booking_reference)
        self.assertEqual(replacement_booking.status, LiveClassBooking.Status.PENDING_PAYMENT)
        duplicate = process_live_class_notification(self.callback(booking), gateway=gateway)
        self.assertTrue(duplicate.duplicate)
        self.assertEqual(gateway.calls, 2)

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
        self.assertEqual(message.attachments[0][2], "application/pdf")
        self.assertTrue(message.attachments[0][1].startswith(b"%PDF"))

        self.assertEqual(deliver_live_class_confirmation.run(), 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_invoice_archive_and_download_are_student_owned(self):
        checkout = self.checkout()
        booking = LiveClassBooking.objects.get(reference=checkout.booking_reference)
        process_live_class_notification(self.callback(booking), gateway=MockPayFastGateway(True))

        with TemporaryDirectory() as directory, override_settings(
            STORAGES={
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
                "default": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                    "OPTIONS": {"location": str(Path(directory) / "admin")},
                },
                "student_private": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                    "OPTIONS": {"location": str(Path(directory) / "student"), "allow_overwrite": True},
                },
            }
        ):
            owner = APIClient()
            owner.force_authenticate(user=SupabaseStudentPrincipal(
                student=self.student,
                supabase_user_id=str(self.student.supabase_user_id),
                email=self.student.email,
            ))
            other = APIClient()
            other.force_authenticate(user=SupabaseStudentPrincipal(
                student=self.other_student,
                supabase_user_id=str(self.other_student.supabase_user_id),
                email=self.other_student.email,
            ))
            url = reverse("live-class-invoice-download", args=[booking.reference])
            self.assertEqual(owner.get(url, secure=True).status_code, 404)
            self.assertEqual(deliver_live_class_confirmation.run(), 1)
            booking.refresh_from_db()

            key = Path("invoices") / str(self.student.supabase_user_id) / f"{booking.invoice_number}.pdf"
            archived = Path(directory, "student", key).read_bytes()
            self.assertTrue(archived.startswith(b"%PDF"))
            self.assertFalse(Path(directory, "admin", key).exists())
            self.assertEqual(archived, mail.outbox[-1].attachments[0][1])
            self.assertEqual(other.get(url, secure=True).status_code, 404)
            response = owner.get(url, secure=True)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Cache-Control"], "private, no-store")
            self.assertEqual(b"".join(response.streaming_content), archived)

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

    def test_reminders_drain_multiple_bookings_in_one_schedule_tick(self):
        for index in range(3):
            slot = TutorAvailabilitySlot.objects.create(
                tutor=self.tutor,
                programme=TutorAvailabilitySlot.Programme.CAPS,
                subject=TutorAvailabilitySlot.Subject.MATHEMATICS,
                level="Grade 12",
                starts_at=timezone.now() + timedelta(minutes=25, seconds=index * 2),
                ends_at=timezone.now() + timedelta(minutes=85, seconds=index * 2),
                zoom_join_url=f"https://zoom.example.test/j/{index + 100000000}",
            )
            booking = LiveClassBooking.objects.create(
                reference=f"LCB-reminder-batch-{index}",
                idempotency_key=f"reminder-batch-{index}",
                student=self.student,
                slot=slot,
                programme=slot.programme,
                subject=slot.subject,
                level=slot.level,
                topic="Algebra",
                status=LiveClassBooking.Status.CONFIRMED,
                confirmation_sent_at=timezone.now(),
                paid_at=timezone.now(),
            )
            self.assertIsNotNone(booking.pk)
        self.assertEqual(deliver_live_class_reminder.run(), 3)
        self.assertEqual(len(mail.outbox), 3)
        self.assertIn("30 minutes", mail.outbox[0].subject)
        self.assertIn("https://zoom.example.test/j/100000000", mail.outbox[0].body)

        self.assertEqual(deliver_live_class_reminder.run(), 0)
        self.assertEqual(len(mail.outbox), 3)

    def test_expired_unpaid_hold_releases_slot(self):
        checkout = self.checkout()
        booking = LiveClassBooking.objects.get(reference=checkout.booking_reference)
        LiveClassBooking.objects.filter(pk=booking.pk).update(hold_expires_at=timezone.now() - timedelta(seconds=1))

        self.assertEqual(expire_live_class_holds.run(), 1)
        booking.refresh_from_db()
        self.assertEqual(booking.status, LiveClassBooking.Status.EXPIRED)

        replacement = self.checkout(
            student=self.other_student,
            key="liveclass-checkout-003",
        )
        replacement_booking = LiveClassBooking.objects.get(reference=replacement.booking_reference)
        self.assertEqual(
            replacement_booking.status,
            LiveClassBooking.Status.PENDING_PAYMENT,
        )
