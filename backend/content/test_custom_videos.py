from __future__ import annotations

import os
import tempfile
import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from content.authentication import SupabaseStudentPrincipal
from content.models import (
    CustomVideoInvoice,
    CustomVideoRequest,
    CustomVideoSettings,
    StudentRecord,
)
from content.services.custom_videos import (
    CustomVideoValidationError,
    _validated_payment_urls,
    create_custom_video_checkout,
    create_custom_video_request,
    process_custom_video_notification,
)
from content.services.payments import PaymentSecurityError
from content.tasks import deliver_custom_video_delivery, deliver_custom_video_invoice


class MockPayFastGateway:
    def __init__(self, result=True):
        self.result = result
        self.calls = 0

    def verify_notification(self, payload):
        self.calls += 1
        del payload
        return self.result


class CustomVideoRequestTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media_directory = tempfile.TemporaryDirectory()
        cls.settings_override = override_settings(
            MEDIA_ROOT=cls.media_directory.name,
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
            DEFAULT_FROM_EMAIL="Amaris Mathematics Academy <noreply@example.test>",
            CUSTOM_VIDEO_PERSISTENT_STORAGE=True,
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                },
                "staticfiles": {
                    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
                },
            },
        )
        cls.settings_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.settings_override.disable()
        cls.media_directory.cleanup()

    def setUp(self):
        self.student = StudentRecord.objects.create(
            supabase_user_id=uuid.UUID("00000000-0000-4000-8000-000000000301"),
            email="video.student@example.test",
            first_name="Video",
            last_name="Student",
        )
        self.settings = CustomVideoSettings.objects.create(
            enabled=True,
            flat_fee=Decimal("321.00"),
            currency="ZAR",
            max_files=3,
            max_file_size_mb=1,
        )

    @staticmethod
    def pdf(name="question.pdf"):
        return SimpleUploadedFile(
            name,
            b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n",
            content_type="application/pdf",
        )

    def create_request(self, key="custom-video-test-001"):
        return create_custom_video_request(
            student=self.student,
            curriculum="caps",
            subject="mathematics",
            grade="12",
            topic="Differential calculus",
            idempotency_key=key,
            files=[self.pdf()],
        )

    def callback(self, request_record, **overrides):
        payload = {
            "m_payment_id": request_record.reference,
            "pf_payment_id": "PF-VIDEO-SANDBOX-001",
            "payment_status": "COMPLETE",
            "amount_gross": "321.00",
            "custom_str1": str(self.student.supabase_user_id),
            "custom_str2": request_record.reference,
            "signature": "synthetic-signature-never-sent",
        }
        payload.update({key: str(value) for key, value in overrides.items()})
        return payload

    @staticmethod
    def authenticated_client(
        student: StudentRecord,
        *,
        provider: str = "test",
    ) -> APIClient:
        client = APIClient()
        client.force_authenticate(
            user=SupabaseStudentPrincipal(
                student=student,
                supabase_user_id=str(student.supabase_user_id),
                email=student.email,
            ),
            token={"provider": provider},
        )
        return client

    def test_public_options_use_modelled_choices_without_inventing_topics(self):
        response = self.client.get(reverse("custom-video-options"), secure=True)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["enabled"])
        self.assertEqual(body["amount"], "321.00")
        self.assertEqual(
            {item["value"] for item in body["curricula"]},
            {"caps", "ieb", "tvet", "university"},
        )
        self.assertEqual(
            {item["value"] for item in body["subjects"]},
            {"mathematics", "mathematical_literacy"},
        )
        self.assertEqual(body["modelled_topics"], [])
        self.assertEqual(body["topic_mode"], "free_text")

    def test_request_stores_private_supporting_file_and_waits_for_server_pricing(self):
        request_record = self.create_request()

        self.assertIsNone(request_record.amount)
        self.assertEqual(request_record.attachments.count(), 1)
        attachment = request_record.attachments.get()
        self.assertEqual(attachment.original_name, "question.pdf")
        self.assertTrue(attachment.file.storage.exists(attachment.file.name))

    def test_enabled_settings_require_an_admin_configured_price(self):
        self.settings.delete()
        with self.assertRaises(ValidationError):
            CustomVideoSettings.objects.create(enabled=True, flat_fee=None)

    def test_unsupported_or_mismatched_files_are_rejected_server_side(self):
        executable = SimpleUploadedFile(
            "malware.exe",
            b"MZnot-an-executable-used-only-for-validation",
            content_type="application/octet-stream",
        )
        with self.assertRaises(CustomVideoValidationError):
            create_custom_video_request(
                student=self.student,
                curriculum="caps",
                subject="mathematics",
                grade="12",
                topic="Algebra",
                idempotency_key="custom-video-bad-001",
                files=[executable],
            )

        fake_pdf = SimpleUploadedFile(
            "fake.pdf",
            b"MZthis-is-not-a-pdf",
            content_type="application/pdf",
        )
        with self.assertRaises(CustomVideoValidationError):
            create_custom_video_request(
                student=self.student,
                curriculum="caps",
                subject="mathematics",
                grade="12",
                topic="Algebra",
                idempotency_key="custom-video-bad-002",
                files=[fake_pdf],
            )

    def test_oversized_file_is_rejected_using_admin_limit(self):
        oversized = SimpleUploadedFile(
            "large.pdf",
            b"%PDF-1.4\n" + (b"x" * (1024 * 1024)),
            content_type="application/pdf",
        )
        with self.assertRaises(CustomVideoValidationError):
            create_custom_video_request(
                student=self.student,
                curriculum="caps",
                subject="mathematics",
                grade="12",
                topic="Algebra",
                idempotency_key="custom-video-large-001",
                files=[oversized],
            )

    def test_checkout_uses_admin_price_and_verified_callback_creates_invoice(self):
        request_record = self.create_request()
        checkout = create_custom_video_checkout(
            student=self.student,
            request_record=request_record,
        )

        request_record.refresh_from_db()
        self.assertEqual(request_record.amount, Decimal("321.00"))
        self.assertEqual(checkout.fields["amount"], "321.00")
        self.assertIn("sandbox.payfast.co.za", checkout.gateway_url)

        result = process_custom_video_notification(
            self.callback(request_record),
            gateway=MockPayFastGateway(True),
        )

        self.assertTrue(result.accepted)
        request_record.refresh_from_db()
        self.assertEqual(request_record.status, CustomVideoRequest.Status.PAID)
        self.assertIsNotNone(request_record.gateway_verified_at)
        invoice = CustomVideoInvoice.objects.get(request=request_record)
        self.assertEqual(invoice.amount, Decimal("321.00"))
        self.assertTrue(invoice.invoice_number.startswith("INV-VIDEO-"))

    def test_tampered_amount_never_marks_request_paid(self):
        request_record = self.create_request()
        create_custom_video_checkout(
            student=self.student,
            request_record=request_record,
        )

        result = process_custom_video_notification(
            self.callback(request_record, amount_gross="1.00"),
            gateway=MockPayFastGateway(True),
        )

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "tampered_amount")
        request_record.refresh_from_db()
        self.assertEqual(
            request_record.status,
            CustomVideoRequest.Status.PENDING_PAYMENT,
        )
        self.assertFalse(CustomVideoInvoice.objects.exists())

    def test_invoice_pdf_is_archived_and_emailed_once_after_verified_payment(self):
        request_record = self.create_request()
        create_custom_video_checkout(
            student=self.student,
            request_record=request_record,
        )
        process_custom_video_notification(
            self.callback(request_record),
            gateway=MockPayFastGateway(True),
        )

        delivered = deliver_custom_video_invoice.run()

        self.assertEqual(delivered, 1)
        request_record.refresh_from_db()
        self.assertIsNotNone(request_record.invoice_sent_at)
        invoice = CustomVideoInvoice.objects.get(request=request_record)
        self.assertTrue(invoice.pdf_file.name.endswith(".pdf"))
        with invoice.pdf_file.open("rb") as pdf_file:
            pdf_bytes = pdf_file.read()
        self.assertTrue(pdf_bytes.startswith(b"%PDF-1.4"))
        self.assertIn(invoice.invoice_number.encode("latin-1"), pdf_bytes)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.student.email])
        self.assertIn(request_record.reference, message.subject)
        self.assertEqual(len(message.attachments), 1)
        attachment = message.attachments[0]
        self.assertTrue(attachment.filename.endswith(".pdf"))
        self.assertEqual(attachment.mimetype, "application/pdf")

        self.assertEqual(deliver_custom_video_invoice.run(), 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_feature_fails_closed_without_persistent_storage(self):
        with override_settings(CUSTOM_VIDEO_PERSISTENT_STORAGE=False):
            options = self.client.get(reverse("custom-video-options"), secure=True)
            self.assertEqual(options.status_code, 200)
            self.assertFalse(options.json()["enabled"])

            with self.assertRaises(CustomVideoValidationError):
                self.create_request(key="custom-video-storage-off-001")

    def test_failed_attachment_database_save_removes_uploaded_object(self):
        before = {
            path.relative_to(self.media_directory.name)
            for path in Path(self.media_directory.name).rglob("*")
            if path.is_file()
        }
        with patch(
            "content.models.CustomVideoRequestAttachment.save",
            side_effect=RuntimeError("synthetic database write failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.create_request(key="custom-video-cleanup-001")

        after = {
            path.relative_to(self.media_directory.name)
            for path in Path(self.media_directory.name).rglob("*")
            if path.is_file()
        }
        self.assertEqual(after, before)
        self.assertFalse(
            CustomVideoRequest.objects.filter(
                idempotency_key="custom-video-cleanup-001"
            ).exists()
        )

    def test_payment_urls_fail_closed_without_notification_endpoint(self):
        with patch.dict(
            os.environ,
            {
                "PUBLIC_SITE_URL": "https://students.example.test",
                "PUBLIC_API_URL": "",
                "PAYFAST_NOTIFY_URL": "",
            },
            clear=False,
        ):
            with self.assertRaises(PaymentSecurityError):
                _validated_payment_urls()

    def test_live_payment_urls_require_https(self):
        with (
            patch("content.services.custom_videos._payfast_mode", return_value="live"),
            patch.dict(
                os.environ,
                {
                    "PAYFAST_CUSTOM_VIDEO_RETURN_URL": "http://students.example.test/request-your-own-video/confirmation",
                    "PAYFAST_CUSTOM_VIDEO_CANCEL_URL": "http://students.example.test/payments/cancelled",
                    "PAYFAST_NOTIFY_URL": "http://api.example.test/api/v1/payfast/itn/",
                },
                clear=False,
            ),
        ):
            with self.assertRaises(PaymentSecurityError):
                _validated_payment_urls()

    def test_other_student_cannot_read_or_checkout_request(self):
        request_record = self.create_request()
        other_student = StudentRecord.objects.create(
            supabase_user_id=uuid.UUID("00000000-0000-4000-8000-000000000302"),
            email="other.video.student@example.test",
            first_name="Other",
            last_name="Student",
        )
        client = self.authenticated_client(other_student)

        status_response = client.get(
            reverse(
                "custom-video-request-status",
                kwargs={"reference": request_record.reference},
            ),
            secure=True,
        )
        checkout_response = client.post(
            reverse(
                "custom-video-checkout",
                kwargs={"reference": request_record.reference},
            ),
            secure=True,
        )

        self.assertEqual(status_response.status_code, 404)
        self.assertEqual(checkout_response.status_code, 404)

    def test_delivery_email_is_sent_once_after_verified_payment(self):
        request_record = self.create_request()
        create_custom_video_checkout(
            student=self.student,
            request_record=request_record,
        )
        result = process_custom_video_notification(
            self.callback(request_record),
            gateway=MockPayFastGateway(True),
        )
        self.assertTrue(result.accepted)

        request_record.refresh_from_db()
        request_record.status = CustomVideoRequest.Status.DELIVERED
        request_record.delivery_url = "https://video.example.test/private/custom-video"
        request_record.save(update_fields=("status", "delivery_url", "updated_at"))

        delivered = deliver_custom_video_delivery.run()

        self.assertEqual(delivered, 1)
        request_record.refresh_from_db()
        self.assertIsNotNone(request_record.delivery_sent_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(request_record.reference, mail.outbox[0].subject)
        self.assertIn(request_record.delivery_url, mail.outbox[0].body)

        self.assertEqual(deliver_custom_video_delivery.run(), 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_duplicate_verified_callback_is_idempotent(self):
        request_record = self.create_request()
        create_custom_video_checkout(
            student=self.student,
            request_record=request_record,
        )
        gateway = MockPayFastGateway(True)

        first = process_custom_video_notification(
            self.callback(request_record),
            gateway=gateway,
        )
        duplicate = process_custom_video_notification(
            self.callback(request_record),
            gateway=gateway,
        )

        self.assertTrue(first.accepted)
        self.assertTrue(duplicate.accepted)
        self.assertTrue(duplicate.duplicate)
        self.assertEqual(CustomVideoInvoice.objects.filter(request=request_record).count(), 1)

    def test_staging_acceptance_payment_requires_github_oidc_and_completes_sandbox_request(self):
        request_record = self.create_request(key="custom-video-acceptance-001")
        create_custom_video_checkout(
            student=self.student,
            request_record=request_record,
        )
        url = reverse(
            "custom-video-acceptance-payment-complete",
            kwargs={"reference": request_record.reference},
        )

        ordinary_client = self.authenticated_client(self.student)
        rejected = ordinary_client.post(url, {}, format="json", secure=True)
        self.assertEqual(rejected.status_code, 403)

        acceptance_client = self.authenticated_client(
            self.student,
            provider="github-actions-oidc",
        )
        completed = acceptance_client.post(url, {}, format="json", secure=True)

        self.assertEqual(completed.status_code, 200)
        body = completed.json()
        self.assertEqual(body["request_reference"], request_record.reference)
        self.assertEqual(body["status"], CustomVideoRequest.Status.PAID)
        self.assertTrue(body["invoice_number"].startswith("INV-VIDEO-"))

        request_record.refresh_from_db()
        self.assertEqual(request_record.status, CustomVideoRequest.Status.PAID)
        self.assertIsNotNone(request_record.gateway_verified_at)
