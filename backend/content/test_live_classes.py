import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from content.admin import TutorAvailabilitySlotAdminForm
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


class TutorAvailabilitySlotAdminFormTests(TestCase):
    def setUp(self):
        self.tutor = get_user_model().objects.create_user(
            username="admin.slot.tutor",
            email="slot.tutor@example.test",
        )
        self.start = (timezone.now() + timedelta(days=2)).replace(second=0, microsecond=0)

    def slot_data(self, start):
        return {
            "tutor": self.tutor.pk,
            "programme": TutorAvailabilitySlot.Programme.CAPS,
            "subject": TutorAvailabilitySlot.Subject.MATHEMATICS,
            "level": "Grade 12",
            "starts_at": timezone.localtime(start).strftime("%Y-%m-%d %H:%M:%S"),
            "duration_hours": 1,
            "zoom_join_url": "https://zoom.example.test/j/123456789",
            "is_active": True,
        }

    def test_add_slot_automatically_ends_after_one_hour(self):
        form = TutorAvailabilitySlotAdminForm(data=self.slot_data(self.start))
        self.assertNotIn("ends_at", form.fields)
        self.assertIn("duration_hours", form.fields)
        self.assertTrue(form.is_valid(), form.errors)
        slot = form.save()
        self.assertEqual(slot.ends_at - slot.starts_at, timedelta(hours=1))
        slot.full_clean()

    def test_changing_start_recalculates_end_time(self):
        slot = TutorAvailabilitySlot.objects.create(
            tutor=self.tutor,
            programme=TutorAvailabilitySlot.Programme.CAPS,
            subject=TutorAvailabilitySlot.Subject.MATHEMATICS,
            level="Grade 12",
            starts_at=self.start,
            ends_at=self.start + timedelta(hours=1),
            zoom_join_url="https://zoom.example.test/j/123456789",
            is_active=True,
        )
        new_start = self.start + timedelta(days=1, minutes=30)
        form = TutorAvailabilitySlotAdminForm(data=self.slot_data(new_start), instance=slot)
        self.assertTrue(form.is_valid(), form.errors)
        updated = form.save()
        self.assertEqual(updated.starts_at, new_start)
        self.assertEqual(updated.ends_at, new_start + timedelta(hours=1))

    def test_model_still_rejects_non_hour_slot(self):
        slot = TutorAvailabilitySlot(
            tutor=self.tutor,
            programme=TutorAvailabilitySlot.Programme.CAPS,
            subject=TutorAvailabilitySlot.Subject.MATHEMATICS,
            level="Grade 12",
            starts_at=self.start,
            ends_at=self.start + timedelta(minutes=45),
            zoom_join_url="https://zoom.example.test/j/123456789",
        )
        with self.assertRaisesRegex(ValidationError, "whole hours"):
            slot.full_clean()

    def test_superadmin_form_explains_automatic_end_time(self):
        model_admin = admin.site._registry[TutorAvailabilitySlot]
        self.assertIn("automatically calculated", model_admin.duration_notice(None))
        self.assertIn("ends_at", model_admin.get_readonly_fields(None))

    def test_superadmin_can_save_slot_without_entering_end_time(self):
        staff = get_user_model().objects.create_superuser(
            username="live.slot.admin",
            email="admin.slot@example.test",
            password="Synthetic-Only-Password-8302",
        )
        self.client.force_login(staff)
        date = timezone.localtime(self.start)
        response = self.client.post(
            reverse("admin:content_tutoravailabilityslot_add"),
            {
                "tutor": str(self.tutor.pk),
                "programme": TutorAvailabilitySlot.Programme.CAPS,
                "subject": TutorAvailabilitySlot.Subject.MATHEMATICS,
                "level": "Grade 12",
                "starts_at_0": date.strftime("%Y-%m-%d"),
                "starts_at_1": date.strftime("%H:%M:%S"),
                "duration_hours": "1",
                "zoom_join_url": "https://zoom.example.test/j/123456789",
                "is_active": "on",
                "_save": "Save",
            },
            secure=True,
        )
        self.assertEqual(response.status_code, 302, response.context)
        slot = TutorAvailabilitySlot.objects.get(tutor=self.tutor)
        self.assertEqual(slot.ends_at - slot.starts_at, timedelta(hours=1))

    def test_tutor_can_choose_two_or_three_hours(self):
        for hours in (2, 3):
            with self.subTest(hours=hours):
                start = self.start + timedelta(days=hours)
                data = self.slot_data(start)
                data["duration_hours"] = hours
                form = TutorAvailabilitySlotAdminForm(data=data)
                self.assertTrue(form.is_valid(), form.errors)
                slot = form.save()
                self.assertEqual(slot.ends_at - slot.starts_at, timedelta(hours=hours))
                self.assertEqual(slot.duration_hours, hours)

    def test_hours_must_be_positive_whole_hours_within_one_day(self):
        for hours in ("0", "-1", "1.5", "25"):
            with self.subTest(hours=hours):
                data = self.slot_data(self.start)
                data["duration_hours"] = hours
                form = TutorAvailabilitySlotAdminForm(data=data)
                self.assertFalse(form.is_valid())
                self.assertIn("duration_hours", form.errors)

    def test_tutor_cannot_offer_overlapping_sessions(self):
        TutorAvailabilitySlot.objects.create(
            tutor=self.tutor,
            programme=TutorAvailabilitySlot.Programme.CAPS,
            subject=TutorAvailabilitySlot.Subject.MATHEMATICS,
            level="Grade 12",
            starts_at=self.start,
            ends_at=self.start + timedelta(hours=3),
            zoom_join_url="https://zoom.example.test/j/123456789",
            is_active=True,
        )
        data = self.slot_data(self.start + timedelta(hours=2))
        data["duration_hours"] = 2
        form = TutorAvailabilitySlotAdminForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("overlaps", str(form.errors))

    def test_cannot_change_hours_after_booking_reserved(self):
        slot = TutorAvailabilitySlot.objects.create(
            tutor=self.tutor,
            programme=TutorAvailabilitySlot.Programme.CAPS,
            subject=TutorAvailabilitySlot.Subject.MATHEMATICS,
            level="Grade 12",
            starts_at=self.start,
            ends_at=self.start + timedelta(hours=2),
            zoom_join_url="https://zoom.example.test/j/123456789",
            is_active=True,
        )
        student = StudentRecord.objects.create(
            supabase_user_id=uuid.UUID("00000000-0000-4000-8000-000000000301"),
            email="reserved@example.test",
            first_name="Reserved",
            last_name="Student",
        )
        LiveClassBooking.objects.create(
            reference="LCB-admin-reserved-test",
            idempotency_key="admin-reserved-test",
            student=student,
            slot=slot,
            programme=slot.programme,
            subject=slot.subject,
            level=slot.level,
            topic="Derivatives",
            amount=Decimal("500.00"),
            status=LiveClassBooking.Status.PENDING_PAYMENT,
        )
        data = self.slot_data(self.start)
        data["duration_hours"] = 3
        form = TutorAvailabilitySlotAdminForm(data=data, instance=slot)
        self.assertFalse(form.is_valid())
        self.assertIn("reserved or paid", str(form.errors))

    def test_superadmin_can_post_three_hour_slot(self):
        staff = get_user_model().objects.create_superuser(
            username="longclass.admin",
            email="longclass.admin@example.test",
            password="Synthetic-Only-Password-8302",
        )
        self.client.force_login(staff)
        date = timezone.localtime(self.start)
        response = self.client.post(
            reverse("admin:content_tutoravailabilityslot_add"),
            {
                "tutor": str(self.tutor.pk),
                "programme": TutorAvailabilitySlot.Programme.CAPS,
                "subject": TutorAvailabilitySlot.Subject.MATHEMATICS,
                "level": "Grade 12",
                "starts_at_0": date.strftime("%Y-%m-%d"),
                "starts_at_1": date.strftime("%H:%M:%S"),
                "duration_hours": "3",
                "zoom_join_url": "https://zoom.example.test/j/123456789",
                "is_active": "on",
                "_save": "Save",
            },
            secure=True,
        )
        self.assertEqual(response.status_code, 302, response.context)
        self.assertEqual(TutorAvailabilitySlot.objects.get(tutor=self.tutor).duration_hours, 3)


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
        self.admin = user_model.objects.create_superuser(
            username="amaris.admin",
            email="admin@example.test",
            password="test-only-admin-password",
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
            "amount_gross": f"{booking.amount:.2f}",
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
        self.assertEqual(slot["tutor_id"], self.tutor.pk)
        self.assertEqual(slot["price"], "250.00")
        self.assertNotIn("zoom_join_url", slot)

    def test_overnight_named_tutor_filter_uses_published_slots(self):
        night_tutor = get_user_model().objects.create_user(
            username="tutor.night", first_name="Night", last_name="Tutor", email="night@example.test"
        )
        tomorrow = timezone.localtime(timezone.now()) + timedelta(days=2)
        start = tomorrow.replace(hour=23, minute=30, second=0, microsecond=0)
        night_slot = TutorAvailabilitySlot.objects.create(
            tutor=night_tutor,
            programme=TutorAvailabilitySlot.Programme.CAPS,
            subject=TutorAvailabilitySlot.Subject.MATHEMATICS,
            level="Grade 12",
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            zoom_join_url="https://zoom.example.test/j/overnight",
        )
        response = self.client.get(reverse("live-class-slots"), {"tutor_id": night_tutor.pk}, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([slot["id"] for slot in response.json()], [night_slot.pk])
        self.assertEqual(response.json()[0]["tutor"], "Night Tutor")
        self.assertNotIn("zoom_join_url", response.json()[0])
        self.assertEqual(self.client.get(reverse("live-class-slots"), {"tutor_id": -5}, secure=True).status_code, 400)

    def test_partial_smtp_outage_keeps_student_invoice_idempotent(self):
        checkout = self.checkout(key="delivery-retry-0001")
        booking = LiveClassBooking.objects.get(reference=checkout.booking_reference)
        process_live_class_notification(self.callback(booking), gateway=MockPayFastGateway(True))
        from content import tasks

        original = tasks._send_live_class_message

        def fail_tutor(booking, **kwargs):
            if kwargs.get("recipients") == [self.tutor.email]:
                raise OSError("Synthetic tutor SMTP failure")
            return original(booking, **kwargs)

        with mock.patch("content.tasks._send_live_class_message", side_effect=fail_tutor):
            with self.assertRaises(OSError):
                deliver_live_class_confirmation.run()

        booking.refresh_from_db()
        self.assertIsNotNone(booking.confirmation_sent_at)
        self.assertIsNone(booking.tutor_confirmation_sent_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(deliver_live_class_confirmation.run(), 2)
        self.assertEqual(len(mail.outbox), 3)
        self.assertEqual(
            [m.to for m in mail.outbox if m.to == [self.student.email]],
            [[self.student.email]],
        )

    def test_legacy_paid_booking_suppresses_new_tutor_admin_alerts(self):
        checkout = self.checkout(key="legacy-booking-00001")
        booking = LiveClassBooking.objects.get(reference=checkout.booking_reference)
        process_live_class_notification(self.callback(booking), gateway=MockPayFastGateway(True))
        booking.staff_notification_required = False
        booking.save(update_fields=("staff_notification_required",))
        self.assertEqual(deliver_live_class_confirmation.run(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.student.email])

    def test_public_availability_ignores_expired_holds_without_writing_booking_state(self):
        checkout = self.checkout(key="expired-read-only-slot-001")
        booking = LiveClassBooking.objects.get(reference=checkout.booking_reference)
        booking.hold_expires_at = timezone.now() - timedelta(seconds=1)
        booking.save(update_fields=("hold_expires_at",))

        # A public GET should expose the freed slot but never perform an
        # UPDATE on payments/bookings. Expiry belongs to the worker/checkout.
        response = self.client.get(reverse("live-class-slots"), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.slot.pk, [slot["id"] for slot in response.json()])
        booking.refresh_from_db()
        self.assertEqual(booking.status, LiveClassBooking.Status.PENDING_PAYMENT)

        self.assertEqual(expire_live_class_holds.run(), 1)
        booking.refresh_from_db()
        self.assertEqual(booking.status, LiveClassBooking.Status.EXPIRED)

    def test_synthetic_full_booking_payment_email_and_reminder_journey(self):
        # No live gateway, SMTP, SMS or Zoom request is made in this test.
        checkout = self.checkout()
        booking = LiveClassBooking.objects.get(reference=checkout.booking_reference)
        self.assertEqual(booking.status, LiveClassBooking.Status.PENDING_PAYMENT)
        self.assertEqual(len(mail.outbox), 0)

        result = process_live_class_notification(
            self.callback(booking),
            gateway=MockPayFastGateway(True),
        )
        self.assertTrue(result.accepted)
        booking.refresh_from_db()
        self.assertEqual(booking.status, LiveClassBooking.Status.CONFIRMED)
        self.assertTrue(booking.invoice_number.startswith("INV-LIVE-"))
        self.assertEqual(len(mail.outbox), 0)

        self.assertEqual(deliver_live_class_confirmation.run(), 3)
        self.assertEqual(len(mail.outbox), 3)
        self.assertIn(booking.invoice_number, mail.outbox[0].body)
        self.assertEqual(mail.outbox[1].to, [self.tutor.email])
        self.assertIn(self.admin.email, mail.outbox[2].bcc)
        self.assertEqual(mail.outbox[0].attachments[0][2], "application/pdf")

        with mock.patch(
            "content.tasks.timezone.now",
            return_value=self.slot.starts_at - timedelta(minutes=29),
        ):
            self.assertEqual(deliver_live_class_reminder.run(), 1)
        self.assertEqual(len(mail.outbox), 4)
        self.assertIn(self.slot.zoom_join_url, mail.outbox[3].body)
        self.assertEqual(deliver_live_class_reminder.run(), 0)

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

    def test_two_and_three_hour_payment_confirmation_invoice_and_reminder(self):
        for hours in (2, 3):
            with self.subTest(hours=hours):
                self.slot.ends_at = self.slot.starts_at + timedelta(hours=hours)
                self.slot.save(update_fields=("ends_at",))
                checkout = self.checkout(key=f"multi-hour-checkout-{hours}")
                booking = LiveClassBooking.objects.get(reference=checkout.booking_reference)
                expected = Decimal("250.00") * hours
                self.assertEqual(booking.amount, expected)
                self.assertEqual(checkout.fields["amount"], f"{expected:.2f}")
                self.assertIn(f"{hours}-hour", checkout.fields["item_name"])
                response = self.client.get(reverse("live-class-slots"), secure=True)
                # Pending unexpired hold hides the reserved slot.
                self.assertEqual(response.json(), [])
                result = process_live_class_notification(
                    self.callback(booking, pf_payment_id=f"PF-LIVE-SANDBOX-{hours}"),
                    gateway=MockPayFastGateway(True),
                )
                self.assertTrue(result.accepted)
                self.assertEqual(deliver_live_class_confirmation.run(), 3)
                self.assertIn(f"Duration: {hours} hour(s)", mail.outbox[0].body)
                # Remove the synthetic booking to test the next duration using the same slot.
                LiveClassBooking.objects.filter(pk=booking.pk).delete()
                mail.outbox.clear()

    def test_overlapping_tutor_checkout_is_blocked(self):
        other = TutorAvailabilitySlot.objects.create(
            tutor=self.tutor,
            programme=TutorAvailabilitySlot.Programme.CAPS,
            subject=TutorAvailabilitySlot.Subject.MATHEMATICS,
            level="Grade 12",
            starts_at=self.slot.starts_at + timedelta(minutes=30),
            ends_at=self.slot.ends_at + timedelta(minutes=30),
            zoom_join_url="https://zoom.example.test/j/987654321",
        )
        # Simulates legacy/imported conflicting slots that bypass admin validation.
        self.assertEqual(other.duration_hours, 1)
        self.checkout(key="one-overlap-reservation-001")
        with self.assertRaisesRegex(PaymentSecurityError, "overlapping hours"):
            create_live_class_checkout(
                student=self.other_student,
                slot=other,
                topic="Trigonometry",
                idempotency_key="other-overlap-reservation-002",
            )

    def test_published_slot_id_can_be_used_at_authenticated_checkout(self):
        slot_response = self.client.get(reverse("live-class-slots"), secure=True)
        slot_id = slot_response.json()[0]["id"]
        self.assertEqual(slot_id, self.slot.pk)
        client = APIClient()
        client.force_authenticate(
            user=SupabaseStudentPrincipal(
                student=self.student,
                supabase_user_id=str(self.student.supabase_user_id),
                email=self.student.email,
            )
        )
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

        self.assertEqual(delivered, 3)
        booking.refresh_from_db()
        self.assertIsNotNone(booking.confirmation_sent_at)
        self.assertIsNotNone(booking.tutor_confirmation_sent_at)
        self.assertIsNotNone(booking.admin_confirmation_sent_at)
        self.assertEqual(len(mail.outbox), 3)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.student.email])
        self.assertIn("confirmed", message.subject.lower())
        self.assertIn(self.slot.zoom_join_url, message.body)
        self.assertIn(booking.invoice_number, message.body)
        self.assertEqual(len(message.attachments), 1)
        self.assertEqual(message.attachments[0][2], "application/pdf")
        self.assertTrue(message.attachments[0][1].startswith(b"%PDF"))
        tutor_message, admin_message = mail.outbox[1:]
        self.assertEqual(tutor_message.to, [self.tutor.email])
        self.assertEqual(tutor_message.attachments, [])
        self.assertIn(self.student.email, tutor_message.body)
        self.assertIn("Differential calculus", tutor_message.body)
        self.assertIn("SAST", tutor_message.body)
        self.assertIn(self.slot.zoom_join_url, tutor_message.body)
        self.assertEqual(admin_message.to, [])
        self.assertIn(self.admin.email, admin_message.bcc)
        self.assertIn(self.student.email, admin_message.body)
        self.assertIn(booking.reference, admin_message.body)
        self.assertIn(self.slot.zoom_join_url, admin_message.body)
        self.assertEqual(len(admin_message.attachments), 1)
        self.assertEqual(admin_message.attachments[0][0], f"{booking.invoice_number}.pdf")
        self.assertEqual(admin_message.attachments[0][2], "application/pdf")
        self.assertEqual(admin_message.attachments[0][1], message.attachments[0][1])

        self.assertEqual(deliver_live_class_confirmation.run(), 0)
        self.assertEqual(len(mail.outbox), 3)

    def test_invoice_archive_and_download_are_student_owned(self):
        checkout = self.checkout()
        booking = LiveClassBooking.objects.get(reference=checkout.booking_reference)
        process_live_class_notification(self.callback(booking), gateway=MockPayFastGateway(True))

        with (
            TemporaryDirectory() as directory,
            override_settings(
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
            ),
        ):
            owner = APIClient()
            owner.force_authenticate(
                user=SupabaseStudentPrincipal(
                    student=self.student,
                    supabase_user_id=str(self.student.supabase_user_id),
                    email=self.student.email,
                )
            )
            other = APIClient()
            other.force_authenticate(
                user=SupabaseStudentPrincipal(
                    student=self.other_student,
                    supabase_user_id=str(self.other_student.supabase_user_id),
                    email=self.other_student.email,
                )
            )
            url = reverse("live-class-invoice-download", args=[booking.reference])
            self.assertEqual(owner.get(url, secure=True).status_code, 404)
            self.assertEqual(deliver_live_class_confirmation.run(), 3)
            booking.refresh_from_db()

            key = Path("invoices") / str(self.student.supabase_user_id) / f"{booking.invoice_number}.pdf"
            archived = Path(directory, "student", key).read_bytes()
            self.assertTrue(archived.startswith(b"%PDF"))
            self.assertFalse(Path(directory, "admin", key).exists())
            self.assertEqual(archived, mail.outbox[0].attachments[0][1])
            self.assertEqual(archived, mail.outbox[2].attachments[0][1])

            # Django Admin downloads the exact same private object as the
            # student's dashboard; staff without superuser rights cannot.
            admin_url = reverse("admin:content_liveclassbooking_invoice", args=[booking.pk])
            self.client.force_login(self.admin)
            admin_response = self.client.get(admin_url, secure=True)
            self.assertEqual(admin_response.status_code, 200)
            self.assertEqual(admin_response["Cache-Control"], "private, no-store")
            self.assertEqual(b"".join(admin_response.streaming_content), archived)
            change_url = reverse("admin:content_liveclassbooking_change", args=[booking.pk])
            self.assertContains(self.client.get(change_url, secure=True), "Download invoice PDF")
            self.tutor.is_staff = True
            self.tutor.save(update_fields=("is_staff",))
            self.client.force_login(self.tutor)
            self.assertEqual(self.client.get(admin_url, secure=True).status_code, 404)

            self.assertEqual(other.get(url, secure=True).status_code, 404)
            response = owner.get(url, secure=True)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Cache-Control"], "private, no-store")
            self.assertEqual(b"".join(response.streaming_content), archived)

            # A completed lesson remains in student order history and its
            # original PDF must remain available without regenerating it.
            booking.status = LiveClassBooking.Status.COMPLETED
            booking.save(update_fields=("status",))
            completed = owner.get(url, secure=True)
            self.assertEqual(completed.status_code, 200)
            self.assertEqual(b"".join(completed.streaming_content), archived)

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
