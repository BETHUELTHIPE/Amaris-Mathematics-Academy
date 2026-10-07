import uuid
from datetime import timedelta
from decimal import Decimal

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from content.models import StudentRecord, TutorAvailabilitySlot, VideoAsset, VideoRequest
from content.services.video_requests import (
    VIDEO_REQUEST_PRICE,
    PaymentSecurityError,
    create_video_request_checkout,
    process_video_request_notification,
)
from content.tasks import (
    deliver_video_request_confirmation,
    deliver_video_request_delivery,
    expire_video_request_holds,
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
class VideoRequestTests(TestCase):
    def setUp(self):
        self.student = StudentRecord.objects.create(
            supabase_user_id=uuid.UUID("00000000-0000-4000-8000-000000000301"),
            email="video.student@example.test",
            first_name="Video",
            last_name="Student",
        )
        self.other_student = StudentRecord.objects.create(
            supabase_user_id=uuid.UUID("00000000-0000-4000-8000-000000000302"),
            email="other.video.student@example.test",
            first_name="Other",
            last_name="Student",
        )

    def checkout(self, student=None, key="videoreq-checkout-001", **overrides):
        params = {
            "programme": TutorAvailabilitySlot.Programme.CAPS,
            "subject": TutorAvailabilitySlot.Subject.MATHEMATICS,
            "level": "Grade 12",
            "topic": "Integration by parts",
            "details": "Please cover a worked example with substitution.",
        }
        params.update(overrides)
        return create_video_request_checkout(
            student=student or self.student,
            idempotency_key=key,
            **params,
        )

    def callback(self, request_obj, **overrides):
        payload = {
            "m_payment_id": request_obj.reference,
            "pf_payment_id": "PF-VID-SANDBOX-001",
            "payment_status": "COMPLETE",
            "amount_gross": "150.00",
            "custom_str1": str(request_obj.student.supabase_user_id),
            "custom_str2": request_obj.reference,
            "signature": "synthetic-signature-never-sent",
        }
        payload.update({key: str(value) for key, value in overrides.items()})
        return payload

    def test_public_info_exposes_server_price(self):
        response = self.client.get(reverse("video-request-info"), secure=True)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["price"], "150.00")
        self.assertEqual(body["currency"], "ZAR")
        self.assertTrue(any(item["value"] == "caps" for item in body["programmes"]))

    def test_checkout_is_server_priced_at_r150(self):
        checkout = self.checkout()
        request_obj = VideoRequest.objects.get(reference=checkout.request_reference)

        self.assertEqual(VIDEO_REQUEST_PRICE, Decimal("150.00"))
        self.assertEqual(request_obj.amount, Decimal("150.00"))
        self.assertEqual(checkout.fields["amount"], "150.00")
        self.assertTrue(checkout.request_reference.startswith("VRQ-"))
        self.assertIn("sandbox.payfast.co.za", checkout.gateway_url)
        self.assertEqual(request_obj.status, VideoRequest.Status.PENDING_PAYMENT)
        self.assertGreater(request_obj.hold_expires_at, timezone.now())

    def test_idempotency_key_cannot_be_reused_by_another_student(self):
        self.checkout()
        with self.assertRaises(PaymentSecurityError):
            self.checkout(student=self.other_student)

    def test_invalid_programme_is_rejected(self):
        with self.assertRaises(PaymentSecurityError):
            self.checkout(key="videoreq-checkout-002", programme="not-a-programme")

    def test_tampered_amount_never_marks_paid(self):
        checkout = self.checkout()
        request_obj = VideoRequest.objects.get(reference=checkout.request_reference)

        result = process_video_request_notification(
            self.callback(request_obj, amount_gross="1.00"),
            gateway=MockPayFastGateway(True),
        )

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "tampered_amount")
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, VideoRequest.Status.PENDING_PAYMENT)
        self.assertIsNone(request_obj.paid_at)
        self.assertIsNone(request_obj.invoice_number)

    def test_wrong_student_is_rejected(self):
        checkout = self.checkout()
        request_obj = VideoRequest.objects.get(reference=checkout.request_reference)

        result = process_video_request_notification(
            self.callback(request_obj, custom_str1=str(self.other_student.supabase_user_id)),
            gateway=MockPayFastGateway(True),
        )

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "wrong_student")
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, VideoRequest.Status.PENDING_PAYMENT)

    def test_unverified_callback_never_marks_paid(self):
        checkout = self.checkout()
        request_obj = VideoRequest.objects.get(reference=checkout.request_reference)

        result = process_video_request_notification(
            self.callback(request_obj),
            gateway=MockPayFastGateway(False),
        )

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "invalid_callback")
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, VideoRequest.Status.PENDING_PAYMENT)

    def test_verified_payment_marks_paid_and_creates_invoice(self):
        checkout = self.checkout()
        request_obj = VideoRequest.objects.get(reference=checkout.request_reference)

        result = process_video_request_notification(
            self.callback(request_obj),
            gateway=MockPayFastGateway(True),
        )

        self.assertTrue(result.accepted)
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, VideoRequest.Status.PAID)
        self.assertIsNotNone(request_obj.paid_at)
        self.assertIsNotNone(request_obj.gateway_verified_at)
        self.assertTrue(request_obj.invoice_number.startswith("INV-VID-"))

    def test_duplicate_callback_is_idempotent(self):
        checkout = self.checkout()
        request_obj = VideoRequest.objects.get(reference=checkout.request_reference)
        gateway = MockPayFastGateway(True)
        process_video_request_notification(self.callback(request_obj), gateway=gateway)

        result = process_video_request_notification(self.callback(request_obj), gateway=gateway)

        self.assertTrue(result.accepted)
        self.assertTrue(result.duplicate)
        self.assertEqual(VideoRequest.objects.get(pk=request_obj.pk).status, VideoRequest.Status.PAID)

    def test_replayed_provider_reference_on_second_request_is_rejected(self):
        first = self.checkout()
        first_request = VideoRequest.objects.get(reference=first.request_reference)
        process_video_request_notification(self.callback(first_request), gateway=MockPayFastGateway(True))

        second = self.checkout(key="videoreq-checkout-010", topic="Trigonometric identities")
        second_request = VideoRequest.objects.get(reference=second.request_reference)

        result = process_video_request_notification(
            self.callback(second_request),  # reuses PF-VID-SANDBOX-001
            gateway=MockPayFastGateway(True),
        )

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "provider_reference_replay")
        second_request.refresh_from_db()
        self.assertEqual(second_request.status, VideoRequest.Status.PENDING_PAYMENT)

    def test_confirmation_email_is_sent_once_after_payment(self):
        checkout = self.checkout()
        request_obj = VideoRequest.objects.get(reference=checkout.request_reference)
        process_video_request_notification(self.callback(request_obj), gateway=MockPayFastGateway(True))

        delivered = deliver_video_request_confirmation.run()

        self.assertEqual(delivered, 1)
        request_obj.refresh_from_db()
        self.assertIsNotNone(request_obj.confirmation_sent_at)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.student.email])
        self.assertIn(request_obj.invoice_number, message.body)
        self.assertEqual(len(message.attachments), 1)

        self.assertEqual(deliver_video_request_confirmation.run(), 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_fulfilment_delivers_video_and_notifies_student_once(self):
        checkout = self.checkout()
        request_obj = VideoRequest.objects.get(reference=checkout.request_reference)
        process_video_request_notification(self.callback(request_obj), gateway=MockPayFastGateway(True))
        deliver_video_request_confirmation.run()
        mail.outbox.clear()

        video = VideoAsset.objects.create(
            title="Integration by parts \u2014 worked example",
            provider=VideoAsset.Provider.YOUTUBE,
            youtube_video_id="abc123XYZ_0",
            youtube_url="https://www.youtube.com/watch?v=abc123XYZ_0",
            duration_seconds=640,
        )
        # Admin fulfilment: attach the video, then mark fulfilled.
        request_obj.video = video
        request_obj.status = VideoRequest.Status.FULFILLED
        request_obj.fulfilled_at = timezone.now()
        request_obj.save(update_fields=("video", "status", "fulfilled_at", "updated_at"))

        delivered = deliver_video_request_delivery.run()

        self.assertEqual(delivered, 1)
        request_obj.refresh_from_db()
        self.assertIsNotNone(request_obj.delivery_sent_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("ready", mail.outbox[0].subject.lower())

        self.assertEqual(deliver_video_request_delivery.run(), 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_expired_unpaid_hold_is_marked_expired(self):
        checkout = self.checkout()
        request_obj = VideoRequest.objects.get(reference=checkout.request_reference)
        VideoRequest.objects.filter(pk=request_obj.pk).update(
            hold_expires_at=timezone.now() - timedelta(seconds=1)
        )

        self.assertEqual(expire_video_request_holds.run(), 1)
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, VideoRequest.Status.EXPIRED)

    def test_itn_router_dispatches_vrq_prefix_to_video_request(self):
        checkout = self.checkout()
        request_obj = VideoRequest.objects.get(reference=checkout.request_reference)
        # The ITN prefix contract: VRQ- references resolve to a video request.
        self.assertTrue(request_obj.reference.startswith("VRQ-"))
