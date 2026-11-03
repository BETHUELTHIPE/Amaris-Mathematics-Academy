"""WhatsApp notification acceptance tests. No external messages are sent."""

import hashlib
import hmac
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from content.authentication import SupabaseStudentPrincipal
from content.models import LiveClassBooking, StudentRecord, TutorAvailabilitySlot
from content.whatsapp import (
    ProviderRateLimitedError,
    WhatsAppDelivery,
    WhatsAppPreference,
    dispatch_whatsapp_booking_notifications,
)


@override_settings(WHATSAPP_NOTIFICATIONS_ENABLED=True)
class WhatsAppBookingTests(TestCase):
    def setUp(self):
        self.tutor = get_user_model().objects.create_user(
            username="whatsapp-tutor", first_name="Lebo", last_name="Mokoena"
        )
        self.student = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(),
            email="whatsapp-student@example.test",
            first_name="Amaris",
            last_name="Student",
            mobile="+27820000001",
        )
        starts = timezone.now() + timedelta(hours=2)
        self.slot = TutorAvailabilitySlot.objects.create(
            tutor=self.tutor,
            programme=TutorAvailabilitySlot.Programme.CAPS,
            subject=TutorAvailabilitySlot.Subject.MATHEMATICS,
            level="Grade 12",
            starts_at=starts,
            ends_at=starts + timedelta(hours=1),
            zoom_join_url="https://zoom.example.test/j/111",
        )
        self.booking = LiveClassBooking.objects.create(
            reference="LCB-WA-UNIT-1",
            idempotency_key="whatsapp-unit-booking-01",
            student=self.student,
            slot=self.slot,
            programme=self.slot.programme,
            subject=self.slot.subject,
            level=self.slot.level,
            topic="Differential calculus",
            amount="250.00",
            status=LiveClassBooking.Status.CONFIRMED,
            paid_at=timezone.now(),
        )
        self.preference = WhatsAppPreference.objects.create(
            student=self.student,
            number="+27820000001",
            opted_in=True,
            consent_recorded_at=timezone.now(),
            consent_source="student_dashboard",
        )

    @patch("content.whatsapp._send_template", return_value="wamid.001")
    def test_paid_booking_confirmation_once_and_without_zoom_secret(self, send):
        self.assertEqual(dispatch_whatsapp_booking_notifications(), 1)
        self.assertEqual(dispatch_whatsapp_booking_notifications(), 0)
        self.assertEqual(send.call_count, 1)
        number, template, parameters = send.call_args.args
        self.assertEqual(number, "+27820000001")
        self.assertEqual(parameters[0], self.booking.reference)
        self.assertIn("SAST", parameters[2])
        self.assertNotIn("zoom.example", str(parameters))
        self.assertEqual(WhatsAppDelivery.objects.get().status, WhatsAppDelivery.Status.SENT)

    @patch("content.whatsapp._send_template", return_value="wamid.002")
    def test_confirmation_and_30_minute_reminder_once(self, send):
        self.slot.starts_at = timezone.now() + timedelta(minutes=25)
        self.slot.ends_at = self.slot.starts_at + timedelta(hours=1)
        self.slot.save(update_fields=["starts_at", "ends_at"])
        self.assertEqual(dispatch_whatsapp_booking_notifications(), 2)
        self.assertEqual(dispatch_whatsapp_booking_notifications(), 0)
        self.assertEqual(send.call_count, 2)
        self.assertEqual(
            set(WhatsAppDelivery.objects.values_list("kind", flat=True)),
            {"confirmation", "reminder"},
        )

    @patch("content.whatsapp._send_template", return_value="wamid.should-not-send")
    def test_pending_payment_and_no_consent_never_send(self, send):
        self.booking.status = LiveClassBooking.Status.PENDING_PAYMENT
        self.booking.paid_at = None
        self.booking.save(update_fields=["status", "paid_at"])
        self.assertEqual(dispatch_whatsapp_booking_notifications(), 0)
        self.assertFalse(send.called)
        self.booking.status = LiveClassBooking.Status.CONFIRMED
        self.booking.paid_at = timezone.now()
        self.booking.save(update_fields=["status", "paid_at"])
        self.preference.opted_in = False
        self.preference.save(update_fields=["opted_in"])
        self.assertEqual(dispatch_whatsapp_booking_notifications(), 0)
        self.assertFalse(send.called)

    @patch("content.whatsapp._send_template")
    def test_only_explicit_429_is_retried(self, send):
        send.side_effect = [ProviderRateLimitedError(), "wamid.retry-ok"]
        self.assertEqual(dispatch_whatsapp_booking_notifications(), 0)
        delivery = WhatsAppDelivery.objects.get()
        self.assertEqual(delivery.status, WhatsAppDelivery.Status.RETRY)
        self.assertEqual(delivery.attempts, 1)
        self.assertIsNotNone(delivery.next_attempt_at)
        self.assertEqual(dispatch_whatsapp_booking_notifications(), 0)
        delivery.next_attempt_at = timezone.now() - timedelta(seconds=1)
        delivery.save(update_fields=["next_attempt_at"])
        self.assertEqual(dispatch_whatsapp_booking_notifications(), 1)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, WhatsAppDelivery.Status.SENT)
        self.assertEqual(delivery.attempts, 2)
        self.assertEqual(send.call_count, 2)

    @patch("content.whatsapp._send_template", side_effect=TimeoutError())
    def test_ambiguous_timeout_is_not_resent(self, send):
        self.assertEqual(dispatch_whatsapp_booking_notifications(), 0)
        self.assertEqual(dispatch_whatsapp_booking_notifications(), 0)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(WhatsAppDelivery.objects.get().status, WhatsAppDelivery.Status.UNKNOWN)

    @patch("content.whatsapp._send_template", return_value="wamid.never")
    def test_opt_out_between_queue_and_delivery(self, send):
        delivery = WhatsAppDelivery.objects.create(
            booking=self.booking,
            preference=self.preference,
            kind=WhatsAppDelivery.Kind.CONFIRMATION,
            slot_start=self.slot.starts_at,
            next_attempt_at=timezone.now(),
        )
        self.preference.opted_in = False
        self.preference.save(update_fields=["opted_in"])
        self.assertEqual(dispatch_whatsapp_booking_notifications(), 0)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, WhatsAppDelivery.Status.SKIPPED)
        self.assertFalse(send.called)

    @patch("content.whatsapp._send_template", return_value="wamid.tutor")
    def test_tutor_and_student_have_separate_opt_ins(self, send):
        WhatsAppPreference.objects.create(
            tutor=self.tutor,
            number="+27820000002",
            opted_in=True,
            consent_recorded_at=timezone.now(),
            consent_source="tutor_account",
        )
        self.assertEqual(dispatch_whatsapp_booking_notifications(), 2)
        self.assertEqual(send.call_count, 2)

    def _signed_webhook(self, body, signed=True):
        raw = json.dumps(body).encode("utf-8")
        digest = hmac.new(b"test-webhook-secret", raw, hashlib.sha256).hexdigest()
        return self.client.post(
            reverse("whatsapp-webhook"),
            data=raw,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=("sha256=" + digest if signed else "sha256=invalid"),
        )

    @override_settings(WHATSAPP_NOTIFICATIONS_ENABLED=False)
    @patch.dict(
        "os.environ",
        {"WHATSAPP_APP_SECRET": "test-webhook-secret", "WHATSAPP_PHONE_NUMBER_ID": "123"},
    )
    def test_signed_stop_disables_consent_without_disabling_email(self):
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "123"},
                                "messages": [{"from": "27820000001", "type": "text", "text": {"body": "STOP"}}],
                            }
                        }
                    ]
                }
            ]
        }
        self.assertEqual(self._signed_webhook(payload, signed=False).status_code, 403)
        self.preference.refresh_from_db()
        self.assertTrue(self.preference.opted_in)
        self.assertEqual(self._signed_webhook(payload).status_code, 200)
        self.preference.refresh_from_db()
        self.assertFalse(self.preference.opted_in)
        self.assertIsNotNone(self.preference.consent_recorded_at)

    @patch.dict(
        "os.environ",
        {"WHATSAPP_APP_SECRET": "test-webhook-secret", "WHATSAPP_PHONE_NUMBER_ID": "123"},
    )
    def test_out_of_order_receipts_do_not_downgrade_read(self):
        delivery = WhatsAppDelivery.objects.create(
            booking=self.booking,
            preference=self.preference,
            kind=WhatsAppDelivery.Kind.CONFIRMATION,
            slot_start=self.slot.starts_at,
            status=WhatsAppDelivery.Status.SENT,
            provider_id="wamid.read",
        )

        def payload(state):
            return {
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "metadata": {"phone_number_id": "123"},
                                    "statuses": [{"id": "wamid.read", "status": state}],
                                }
                            }
                        ]
                    }
                ]
            }

        self.assertEqual(self._signed_webhook(payload("read")).status_code, 200)
        self.assertEqual(self._signed_webhook(payload("delivered")).status_code, 200)
        self.assertEqual(self._signed_webhook(payload("failed")).status_code, 200)
        delivery.refresh_from_db()
        self.assertEqual(delivery.receipt_status, "read")
        self.assertEqual(delivery.status, WhatsAppDelivery.Status.SENT)

    def test_student_can_save_and_withdraw_explicit_consent(self):
        api = APIClient()
        api.force_authenticate(
            user=SupabaseStudentPrincipal(
                student=self.student,
                supabase_user_id=str(self.student.supabase_user_id),
                email=self.student.email,
            )
        )
        endpoint = reverse("student-whatsapp-preference")
        response = api.post(endpoint, {"number": "+27820000005", "opted_in": True}, format="json")
        self.assertEqual(response.status_code, 200)
        self.preference.refresh_from_db()
        self.assertEqual(self.preference.number, "+27820000005")
        self.assertTrue(self.preference.opted_in)
        response = api.post(endpoint, {"number": "", "opted_in": False}, format="json")
        self.assertEqual(response.status_code, 200)
        self.preference.refresh_from_db()
        self.assertFalse(self.preference.opted_in)
