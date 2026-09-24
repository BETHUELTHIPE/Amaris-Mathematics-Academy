import uuid
from decimal import Decimal

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from content.models import (
    CustomVideoInvoice,
    CustomVideoRequest,
    CustomVideoServiceSettings,
    SiteSettings,
    StudentRecord,
    TutorAvailabilitySlot,
)
from content.services.custom_videos import (
    PaymentSecurityError,
    create_custom_video_checkout,
    create_custom_video_request,
    process_custom_video_notification,
)
from content.tasks import deliver_custom_video_notifications


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
    PAYFAST_MODE="sandbox",
    PAYFAST_MERCHANT_ID="10000100",
    PAYFAST_MERCHANT_KEY="46f0cd694581a",
    PAYFAST_PASSPHRASE="synthetic-passphrase",
    PUBLIC_SITE_URL="https://students.example.test",
    PUBLIC_API_URL="https://api.example.test",
    CUSTOM_VIDEO_NOTIFICATION_EMAILS=["video-team@example.test"],
)
class CustomVideoRequestTests(TestCase):
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
        self.settings = CustomVideoServiceSettings.objects.create(
            enabled=True,
            flat_fee=Decimal("399.00"),
            currency="ZAR",
            max_files=3,
            max_file_size_mb=1,
        )
        SiteSettings.objects.create(
            site_name="Amaris Mathematics Academy",
            phone="071 415 6665",
            email="academy@example.test",
            address="Pretoria, Gauteng",
        )

    @staticmethod
    def pdf(name="source.pdf", content=b"%PDF-1.4\nsynthetic"):
        return SimpleUploadedFile(name, content, content_type="application/pdf")

    @staticmethod
    def png(name="diagram.png"):
        return SimpleUploadedFile(
            name,
            b"\x89PNG\r\n\x1a\n" + b"synthetic-image",
            content_type="image/png",
        )

    def create_request(self, *, key="custom-video-001", files=None, **overrides):
        values = {
            "student": self.student,
            "programme": TutorAvailabilitySlot.Programme.CAPS,
            "subject": TutorAvailabilitySlot.Subject.MATHEMATICS,
            "level": "Grade 12",
            "topic": "Differential calculus",
            "idempotency_key": key,
            "files": [self.pdf()] if files is None else files,
        }
        values.update(overrides)
        return create_custom_video_request(**values)

    def callback(self, video_request, **overrides):
        payload = {
            "m_payment_id": video_request.reference,
            "pf_payment_id": "PF-VIDEO-SANDBOX-001",
            "payment_status": "COMPLETE",
            "amount_gross": f"{video_request.amount:.2f}",
            "custom_str1": str(video_request.student.supabase_user_id),
            "custom_str2": video_request.reference,
            "signature": "synthetic-signature-never-sent",
        }
        payload.update({key: str(value) for key, value in overrides.items()})
        return payload

    def test_options_do_not_invent_caps_topics_or_price_when_disabled(self):
        self.settings.enabled = False
        self.settings.save(update_fields=("enabled", "updated_at"))

        response = self.client.get(reverse("custom-video-options"), secure=True)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["caps_mathematics_topics"], [])
        self.assertEqual(payload["topic_source"], "free_text")
        self.assertIsNone(payload["price"])
        self.assertFalse(payload["checkout_enabled"])

    def test_request_requires_at_least_one_supporting_file(self):
        with self.assertRaisesMessage(PaymentSecurityError, "At least one supporting file"):
            self.create_request(files=[])

    def test_request_stores_multiple_validated_files(self):
        video_request = self.create_request(files=[self.pdf(), self.png()])

        self.assertEqual(video_request.supporting_files.count(), 2)
        self.assertSetEqual(
            set(video_request.supporting_files.values_list("original_name", flat=True)),
            {"source.pdf", "diagram.png"},
        )

    def test_disguised_png_and_unsupported_extension_are_rejected(self):
        fake_png = SimpleUploadedFile(
            "not-really.png",
            b"<html>not an image</html>",
            content_type="image/png",
        )
        with self.assertRaisesMessage(PaymentSecurityError, "valid PNG signature"):
            self.create_request(key="custom-video-002", files=[fake_png])

        executable = SimpleUploadedFile(
            "payload.exe",
            b"MZsynthetic",
            content_type="application/octet-stream",
        )
        with self.assertRaisesMessage(PaymentSecurityError, "Unsupported file type"):
            self.create_request(key="custom-video-003", files=[executable])

    def test_oversized_upload_is_rejected_server_side(self):
        oversized = SimpleUploadedFile(
            "large.pdf",
            b"%PDF-1.4\n" + (b"x" * (1024 * 1024 + 1)),
            content_type="application/pdf",
        )
        with self.assertRaisesMessage(PaymentSecurityError, "exceeds the 1 MB"):
            self.create_request(key="custom-video-004", files=[oversized])

    def test_caps_and_ieb_are_limited_to_supported_school_grades(self):
        with self.assertRaisesMessage(PaymentSecurityError, "Grade 10, 11 or 12"):
            self.create_request(key="custom-video-005", level="Grade 9")

    def test_checkout_uses_admin_configured_fee_and_never_a_client_price(self):
        video_request = self.create_request()

        checkout = create_custom_video_checkout(
            student=self.student,
            video_request=video_request,
        )
        video_request.refresh_from_db()

        self.assertEqual(video_request.amount, Decimal("399.00"))
        self.assertEqual(checkout.fields["amount"], "399.00")
        self.assertIn("sandbox.payfast.co.za", checkout.gateway_url)
        self.assertEqual(video_request.status, CustomVideoRequest.Status.PENDING_PAYMENT)

        with self.assertRaises(PaymentSecurityError):
            create_custom_video_checkout(
                student=self.other_student,
                video_request=video_request,
            )

    def test_checkout_fails_closed_when_admin_price_is_not_enabled(self):
        video_request = self.create_request()
        self.settings.enabled = False
        self.settings.save(update_fields=("enabled", "updated_at"))

        with self.assertRaisesMessage(PaymentSecurityError, "pricing is not configured"):
            create_custom_video_checkout(
                student=self.student,
                video_request=video_request,
            )

    def test_tampered_amount_never_marks_request_paid(self):
        video_request = self.create_request()
        create_custom_video_checkout(student=self.student, video_request=video_request)
        video_request.refresh_from_db()

        result = process_custom_video_notification(
            self.callback(video_request, amount_gross="1.00"),
            gateway=MockPayFastGateway(True),
        )

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "tampered_amount")
        video_request.refresh_from_db()
        self.assertEqual(video_request.status, CustomVideoRequest.Status.PENDING_PAYMENT)
        self.assertIsNone(video_request.invoice_number)

    def test_verified_callback_creates_invoice_and_is_idempotent(self):
        video_request = self.create_request()
        create_custom_video_checkout(student=self.student, video_request=video_request)
        video_request.refresh_from_db()

        with self.captureOnCommitCallbacks(execute=False):
            result = process_custom_video_notification(
                self.callback(video_request),
                gateway=MockPayFastGateway(True),
            )

        self.assertTrue(result.accepted)
        video_request.refresh_from_db()
        self.assertEqual(video_request.status, CustomVideoRequest.Status.PAID)
        self.assertTrue(video_request.invoice_number.startswith("INV-VIDEO-"))
        self.assertTrue(CustomVideoInvoice.objects.filter(video_request=video_request).exists())

        duplicate = process_custom_video_notification(
            self.callback(video_request),
            gateway=MockPayFastGateway(True),
        )
        self.assertTrue(duplicate.accepted)
        self.assertTrue(duplicate.duplicate)

    def test_notification_emails_student_invoice_and_admin(self):
        video_request = self.create_request()
        create_custom_video_checkout(student=self.student, video_request=video_request)
        video_request.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=False):
            process_custom_video_notification(
                self.callback(video_request),
                gateway=MockPayFastGateway(True),
            )

        delivered = deliver_custom_video_notifications.run(str(video_request.pk))

        self.assertEqual(delivered, 2)
        video_request.refresh_from_db()
        self.assertIsNotNone(video_request.confirmation_sent_at)
        self.assertIsNotNone(video_request.admin_notification_sent_at)
        self.assertEqual(len(mail.outbox), 2)

        student_message = next(message for message in mail.outbox if message.to == [self.student.email])
        self.assertIn("confirmed", student_message.subject.lower())
        self.assertTrue(student_message.alternatives)
        self.assertIn("Amaris Mathematics Academy", student_message.alternatives[0].content)
        self.assertEqual(len(student_message.attachments), 1)
        self.assertTrue(student_message.attachments[0][0].endswith(".pdf"))
        self.assertTrue(student_message.attachments[0][1].startswith(b"%PDF-1.4"))

        admin_message = next(
            message for message in mail.outbox if message.to == ["video-team@example.test"]
        )
        self.assertIn(video_request.reference, admin_message.subject)
        self.assertTrue(admin_message.alternatives)
