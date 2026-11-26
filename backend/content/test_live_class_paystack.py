import hashlib
import hmac
import json
import time
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from content.authentication import SupabaseStudentPrincipal
from content.models import LiveClassBooking, StudentRecord, TutorAvailabilitySlot
from content.services import paystack
from content.services.live_classes import process_live_class_notification

TEST_KEY = "sk_test_synthetic"
TEST_WEBHOOK_SECRET = "whsec_synthetic"
HOSTED_CHECKOUT = "https://checkout.paystack.com/synthetic"
PAYSTACK_SETTINGS = {
    "PAYSTACK_ENABLED": "true",
    "PAYSTACK_MODE": "test",
    "PAYSTACK_SECRET_KEY": TEST_KEY,
    "PAYSTACK_WEBHOOK_SECRET": TEST_WEBHOOK_SECRET,
    "PUBLIC_SITE_URL": "https://staging.example.test",
}


@mock.patch.dict("os.environ", PAYSTACK_SETTINGS)
class LiveClassPaystackTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        tutor = get_user_model().objects.create_user(username="paystack.tutor")
        starts_at = (timezone.now() + timedelta(days=1)).replace(second=0, microsecond=0)
        cls.slot = TutorAvailabilitySlot.objects.create(
            tutor=tutor,
            programme=TutorAvailabilitySlot.Programme.CAPS,
            subject=TutorAvailabilitySlot.Subject.MATHEMATICS,
            level="Grade 12",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=2),
            zoom_join_url="https://zoom.example.test/j/synthetic",
        )
        cls.student = StudentRecord.objects.create(
            supabase_user_id="00000000-0000-4000-8000-000000000500",
            email="booking@example.test",
            first_name="Test",
            last_name="Student",
        )

    def setUp(self):
        self.student_api = APIClient()
        self.student_api.force_authenticate(
            SupabaseStudentPrincipal(self.student, str(self.student.supabase_user_id), self.student.email)
        )

    def checkout(self, provider="paystack"):
        return self.student_api.post(
            reverse("live-class-checkout"),
            {
                "slot_id": self.slot.pk,
                "topic": "Algebra",
                "idempotency_key": "synthetic_attempt",
                "payment_provider": provider,
                "amount": "1.00",
                "email": "ignored@example.test",
            },
            format="json",
            secure=True,
        )

    def initialize(self):
        with mock.patch.object(paystack, "_request", side_effect=self.initialize_response) as gateway:
            response = self.checkout()
        self.assertEqual(response.status_code, 201, response.content)
        return response, gateway

    @staticmethod
    def initialize_response(path, *, payload):
        return {"authorization_url": HOSTED_CHECKOUT, "reference": payload["reference"]}

    def callback(self, reference, *, modern=False, age=0, valid=True):
        body = json.dumps({"event": "charge.success", "data": {"reference": reference}}).encode()
        if modern:
            timestamp = str(int(time.time()) - age)
            digest = hmac.new(
                TEST_WEBHOOK_SECRET.encode(), timestamp.encode() + b"." + body, hashlib.sha512
            ).hexdigest()
            headers = {"HTTP_PAYSTACK_SIGNATURE": f"t={timestamp},v1=whk_test:{digest}"}
        else:
            digest = hmac.new(TEST_KEY.encode(), body, hashlib.sha512).hexdigest()
            headers = {"HTTP_X_PAYSTACK_SIGNATURE": digest if valid else "0" * 128}
        return self.client.post(
            reverse("paystack-webhook"), body, content_type="application/json", secure=True, **headers
        )

    @staticmethod
    def successful_payment(reference):
        return {
            "reference": reference,
            "status": "success",
            "domain": "test",
            "currency": "ZAR",
            "amount": 50000,
            "id": 1234,
        }

    def test_checkout_uses_registered_email_and_slot_price_and_reuses_provider_session(self):
        with mock.patch.object(paystack, "_request", side_effect=self.initialize_response) as gateway:
            first = self.checkout()
            second = self.checkout()
            change = self.checkout("payfast")
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(second.status_code, 201, second.content)
        self.assertEqual(change.status_code, 400, change.content)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(first.json()["payment_provider"], "paystack")
        self.assertEqual(first.json()["booking"]["duration_minutes"], 120)
        self.assertEqual(first.json()["gateway_url"], HOSTED_CHECKOUT)
        gateway.assert_called_once()
        payload = gateway.call_args.kwargs["payload"]
        self.assertEqual(payload["email"], self.student.email)
        self.assertEqual(payload["amount"], 50000)
        self.assertEqual(payload["currency"], "ZAR")
        self.assertTrue(paystack.BOOKING_REFERENCE.fullmatch(payload["reference"]))
        self.assertEqual(LiveClassBooking.objects.count(), 1)

    def test_disabled_provider_or_incomplete_account_creates_no_hold(self):
        with mock.patch.dict("os.environ", {"PAYSTACK_ENABLED": "false"}):
            options = self.student_api.get(reverse("live-class-checkout"), secure=True)
            self.assertEqual(options.json(), {"paystack_enabled": False})
            self.assertEqual(self.checkout().status_code, 400)
        self.student_api.force_authenticate(
            SupabaseStudentPrincipal(self.student, str(self.student.supabase_user_id), self.student.email, False)
        )
        self.assertEqual(self.checkout().status_code, 400)
        self.assertFalse(LiveClassBooking.objects.exists())

    def test_verified_webhooks_confirm_once_and_reuse_booking_invoice(self):
        response, _ = self.initialize()
        reference = response.json()["booking_reference"]
        booking = LiveClassBooking.objects.get(reference=reference)
        self.assertFalse(booking.invoice_number)
        status_url = reverse("live-class-booking-status", args=[reference])
        self.assertEqual(self.student_api.get(status_url, secure=True).json()["zoom_join_url"], "")
        with mock.patch.object(paystack, "_request", return_value=self.successful_payment(reference)) as gateway:
            self.assertEqual(self.callback(reference, valid=False).status_code, 403)
            self.assertEqual(self.callback(reference, modern=True, age=600).status_code, 403)
            gateway.assert_not_called()
            self.assertEqual(self.callback(reference, modern=True).status_code, 200)
            booking.refresh_from_db()
            self.assertEqual(booking.status, LiveClassBooking.Status.CONFIRMED)
            self.assertTrue(booking.invoice_number)
            invoice_number = booking.invoice_number
            self.assertEqual(self.callback(reference).status_code, 200)
            booking.refresh_from_db()
            self.assertEqual(booking.invoice_number, invoice_number)
            self.assertEqual(booking.provider_reference, "1234")
            confirmed = self.student_api.get(status_url, secure=True).json()
            self.assertEqual(confirmed["invoice_number"], invoice_number)
            self.assertEqual(confirmed["zoom_join_url"], self.slot.zoom_join_url)
            self.assertEqual(gateway.call_count, 2)

    def test_invalid_verification_and_cross_provider_callbacks_cannot_confirm(self):
        response, _ = self.initialize()
        reference = response.json()["booking_reference"]
        booking = LiveClassBooking.objects.get(reference=reference)
        for field, value in (("amount", 49999), ("currency", "USD"), ("domain", "live"), ("status", "pending")):
            with self.subTest(field=field):
                data = {**self.successful_payment(reference), field: value}
                with mock.patch.object(paystack, "_request", return_value=data):
                    self.assertEqual(self.callback(reference).status_code, 400)
        gateway = mock.Mock()
        result = process_live_class_notification(
            {"m_payment_id": reference, "pf_payment_id": "1234", "payment_status": "COMPLETE"},
            gateway=gateway,
        )
        self.assertEqual(result.reason, "wrong_payment_provider")
        gateway.verify_notification.assert_not_called()
        booking.refresh_from_db()
        self.assertEqual(booking.status, LiveClassBooking.Status.PENDING_PAYMENT)
        self.assertFalse(booking.invoice_number)

    def test_verified_late_payment_goes_to_review_with_no_invoice(self):
        response, _ = self.initialize()
        reference = response.json()["booking_reference"]
        LiveClassBooking.objects.filter(reference=reference).update(
            hold_expires_at=timezone.now() - timedelta(seconds=1)
        )
        with mock.patch.object(paystack, "_request", return_value=self.successful_payment(reference)):
            self.assertEqual(self.callback(reference).status_code, 200)
        booking = LiveClassBooking.objects.get(reference=reference)
        self.assertEqual(booking.status, LiveClassBooking.Status.PAYMENT_REVIEW)
        self.assertTrue(booking.paid_at)
        self.assertFalse(booking.invoice_number)

    def test_provider_initialization_failure_keeps_same_booking_reference_for_retry(self):
        with mock.patch.object(paystack, "_request", side_effect=paystack.PaystackUnavailable):
            self.assertEqual(self.checkout().status_code, 503)
        booking = LiveClassBooking.objects.get()
        self.assertFalse(booking.paystack_checkout_url)
        response, _ = self.initialize()
        self.assertEqual(response.json()["booking_reference"], booking.reference)
        self.assertEqual(LiveClassBooking.objects.count(), 1)
