import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from content.authentication import SupabaseStudentPrincipal
from content.models import StudentRecord, VideoRequest, VideoRequestDocument
from content.services.payments import PaymentSecurityError
from content.services.video_requests import (
    create_video_request_checkout,
    process_video_request_notification,
    video_request_queue_position,
)
from content.tasks import deliver_video_request_notifications, expire_unpaid_video_requests


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
class VideoRequestWorkflowTests(TestCase):
    def setUp(self):
        self.storage_directory = TemporaryDirectory()
        self.addCleanup(self.storage_directory.cleanup)
        self.storage_override = override_settings(
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "student_private": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                    "OPTIONS": {
                        "location": self.storage_directory.name,
                        "allow_overwrite": True,
                    },
                },
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
            }
        )
        self.storage_override.enable()
        self.addCleanup(self.storage_override.disable)
        self.student = StudentRecord.objects.create(
            supabase_user_id=uuid.UUID("00000000-0000-4000-8000-000000000301"),
            email="video.student@example.test",
            first_name="Video",
            last_name="Student",
        )
        self.other_student = StudentRecord.objects.create(
            supabase_user_id=uuid.UUID("00000000-0000-4000-8000-000000000302"),
            email="other.video@example.test",
            first_name="Other",
            last_name="Student",
        )

    def create_checkout(self, *, student=None, key="video-request-001", request_type="chapter_topic", documents=()):
        return create_video_request_checkout(
            student=student or self.student,
            programme="caps",
            subject="mathematics",
            level="Grade 12",
            topic="Differential calculus",
            request_type=request_type,
            instructions="Explain every step and show an exam method.",
            explanation_style="Worked examples",
            preferred_duration_minutes=60,
            idempotency_key=key,
            documents=documents,
        )

    def callback(self, request, **overrides):
        payload = {
            "m_payment_id": request.reference,
            "pf_payment_id": f"PF-{request.pk.hex[:12]}",
            "payment_status": "COMPLETE",
            "amount_gross": f"{request.amount:.2f}",
            "custom_str1": str(request.student.supabase_user_id),
            "custom_str2": request.reference,
            "signature": "synthetic-signature-never-sent",
        }
        payload.update({key: str(value) for key, value in overrides.items()})
        return payload

    def authenticated_client(self, student=None):
        student = student or self.student
        client = APIClient()
        client.force_authenticate(
            user=SupabaseStudentPrincipal(
                student=student,
                supabase_user_id=str(student.supabase_user_id),
                email=student.email,
            )
        )
        return client

    def pay(self, request):
        result = process_video_request_notification(self.callback(request), gateway=MockPayFastGateway())
        request.refresh_from_db()
        return result

    def test_checkout_is_server_priced_and_stores_private_document_metadata(self):
        document = SimpleUploadedFile(
            "calculus-paper.pdf",
            b"%PDF-1.4\nsynthetic test document\n%%EOF",
            content_type="application/pdf",
        )
        checkout = self.create_checkout(documents=[document])
        request = VideoRequest.objects.get(reference=checkout.request_reference)

        self.assertEqual(request.amount, Decimal("450.00"))
        self.assertEqual(checkout.fields["amount"], "450.00")
        self.assertIn("sandbox.payfast.co.za", checkout.gateway_url)
        stored = request.documents.get()
        self.assertEqual(stored.original_name, "calculus-paper.pdf")
        self.assertTrue(stored.storage_path.startswith(f"{self.student.supabase_user_id}/video-requests/"))
        self.assertTrue(Path(self.storage_directory.name, stored.storage_path).exists())

    @override_settings(
        SUPABASE_S3_STUDENT_BUCKET="Amaris Mathematics Academy",
        SUPABASE_S3_ENDPOINT_URL="https://example.supabase.co/storage/v1/s3",
    )
    def test_resumable_document_is_registered_only_after_private_storage_verification(self):
        checkout = self.create_checkout(key="video-large-doc-001")
        item = VideoRequest.objects.get(reference=checkout.request_reference)
        path = f"{self.student.supabase_user_id}/video-requests/{item.pk}/documents/" f"{uuid.uuid4()}.pdf"
        body = b"%PDF-1.4\nSynthetic private file\n%%EOF\n"
        self.assertEqual(storages["student_private"].save(path, ContentFile(body)), path)
        payload = {
            "storage_path": path,
            "original_name": "paper.pdf",
            "content_type": "application/pdf",
            "size_bytes": len(body),
        }
        url = reverse("video-request-document-register", args=[item.reference])
        registered = self.authenticated_client().post(url, payload, format="json", secure=True)
        self.assertEqual(registered.status_code, 201)
        self.assertEqual(item.documents.count(), 1)
        self.assertEqual(item.documents.get().storage_path, path)
        self.assertEqual(
            self.authenticated_client().post(url, payload, format="json", secure=True).status_code,
            201,
        )
        self.assertEqual(item.documents.count(), 1)
        denied = self.authenticated_client(self.other_student).post(url, payload, format="json", secure=True)
        self.assertNotEqual(denied.status_code, 201)
        self.assertEqual(item.documents.count(), 1)

    @override_settings(
        SUPABASE_S3_STUDENT_BUCKET="Amaris Mathematics Academy",
        SUPABASE_S3_ENDPOINT_URL="https://example.supabase.co/storage/v1/s3",
    )
    def test_resumable_document_rejects_spoofed_paths_types_and_sizes(self):
        item = VideoRequest.objects.get(reference=self.create_checkout(key="video-large-bad-001").request_reference)
        path = f"{self.student.supabase_user_id}/video-requests/{item.pk}/documents/" f"{uuid.uuid4()}.pdf"
        self.assertEqual(storages["student_private"].save(path, ContentFile(b"NOT A PDF")), path)
        url = reverse("video-request-document-register", args=[item.reference])
        metadata = {
            "storage_path": path,
            "original_name": "notes.pdf",
            "content_type": "application/pdf",
            "size_bytes": 9,
        }
        bad_magic = self.authenticated_client().post(url, metadata, format="json", secure=True)
        self.assertEqual(bad_magic.status_code, 400)
        wrong_owner = self.authenticated_client().post(
            url,
            {
                **metadata,
                "storage_path": metadata["storage_path"].replace(
                    str(self.student.supabase_user_id), str(self.other_student.supabase_user_id)
                ),
            },
            format="json",
            secure=True,
        )
        self.assertEqual(wrong_owner.status_code, 400)
        oversized = self.authenticated_client().post(
            url,
            {**metadata, "size_bytes": 1024 * 1024 * 1024 + 1},
            format="json",
            secure=True,
        )
        self.assertEqual(oversized.status_code, 400)
        self.assertFalse(item.documents.exists())

    def test_exam_and_complete_content_prices_are_server_owned(self):
        exam = self.create_checkout(key="video-exam-001", request_type="previous_exam")
        content = self.create_checkout(key="video-content-001", request_type="complete_content")
        self.assertEqual(VideoRequest.objects.get(reference=exam.request_reference).amount, Decimal("1800.00"))
        self.assertEqual(VideoRequest.objects.get(reference=content.request_reference).amount, Decimal("1800.00"))

    def test_rejects_spoofed_or_oversized_documents(self):
        spoofed = SimpleUploadedFile("fake.pdf", b"not a pdf", content_type="application/pdf")
        with self.assertRaises(PaymentSecurityError):
            self.create_checkout(key="video-doc-bad-001", documents=[spoofed])
        oversized = SimpleUploadedFile(
            "large.pdf",
            b"%PDF-" + b"x" * (10 * 1024 * 1024),
            content_type="application/pdf",
        )
        with self.assertRaises(PaymentSecurityError):
            self.create_checkout(key="video-doc-big-001", documents=[oversized])

    def test_verified_payment_creates_fifo_ticket_and_invoice(self):
        checkout = self.create_checkout()
        request = VideoRequest.objects.get(reference=checkout.request_reference)
        result = self.pay(request)

        self.assertTrue(result.accepted)
        self.assertEqual(request.status, VideoRequest.Status.QUEUED)
        self.assertIsNotNone(request.gateway_verified_at)
        self.assertIsNotNone(request.queue_entered_at)
        self.assertRegex(request.ticket_number, r"^AMARIS-VID-\d{4}-[A-F0-9]{8}$")
        self.assertRegex(request.invoice_number, r"^INV-VID-\d{8}-[A-F0-9]{10}$")
        self.assertEqual(video_request_queue_position(request), 1)

    def test_callback_rejects_tampered_amount_and_student(self):
        request = VideoRequest.objects.get(reference=self.create_checkout().request_reference)
        amount_result = process_video_request_notification(
            self.callback(request, amount_gross="1.00"),
            gateway=MockPayFastGateway(),
        )
        student_result = process_video_request_notification(
            self.callback(request, custom_str1=str(self.other_student.supabase_user_id)),
            gateway=MockPayFastGateway(),
        )
        self.assertFalse(amount_result.accepted)
        self.assertEqual(amount_result.reason, "tampered_amount")
        self.assertFalse(student_result.accepted)
        self.assertEqual(student_result.reason, "wrong_student")

    def test_late_verified_payment_requires_manual_review(self):
        request = VideoRequest.objects.get(reference=self.create_checkout().request_reference)
        VideoRequest.objects.filter(pk=request.pk).update(payment_expires_at=timezone.now() - timedelta(seconds=1))
        request.refresh_from_db()
        result = self.pay(request)
        self.assertTrue(result.accepted)
        self.assertEqual(request.status, VideoRequest.Status.PAYMENT_REVIEW)
        self.assertIsNone(request.ticket_number)

    def test_student_status_endpoint_prevents_cross_student_access(self):
        request = VideoRequest.objects.get(reference=self.create_checkout().request_reference)
        self.pay(request)
        own = self.authenticated_client().get(reverse("video-request-status", args=[request.reference]), secure=True)
        other = self.authenticated_client(self.other_student).get(
            reverse("video-request-status", args=[request.reference]),
            secure=True,
        )
        self.assertEqual(own.status_code, 200)
        self.assertEqual(own.data["queue_position"], 1)
        self.assertNotIn("provider_reference", own.data)
        self.assertNotIn("student", own.data)
        self.assertEqual(other.status_code, 404)

    def test_ready_video_is_released_only_to_owner_without_raw_url(self):
        request = VideoRequest.objects.get(reference=self.create_checkout().request_reference)
        self.pay(request)
        request.status = VideoRequest.Status.READY
        request.video_external_id = "privateYoutubeId"
        request.video_ready_at = timezone.now()
        request.full_clean()
        request.save()

        response = self.authenticated_client().get(
            reverse("video-request-status", args=[request.reference]),
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["video"]["youtube_video_id"], "privateYoutubeId")
        self.assertNotIn("youtube.com", str(response.data))

    def test_ready_status_requires_private_video_reference(self):
        request = VideoRequest.objects.get(reference=self.create_checkout().request_reference)
        request.status = VideoRequest.Status.READY
        with self.assertRaises(ValidationError):
            request.full_clean()

    def test_unpaid_request_cannot_be_moved_into_fulfilment(self):
        request = VideoRequest.objects.get(reference=self.create_checkout().request_reference)
        request.status = VideoRequest.Status.QUEUED
        with self.assertRaises(ValidationError):
            request.full_clean()

    def test_notifications_attach_invoice_then_send_ready_message(self):
        request = VideoRequest.objects.get(reference=self.create_checkout().request_reference)
        self.pay(request)
        self.assertEqual(deliver_video_request_notifications.run(), 2)
        request.refresh_from_db()
        self.assertIsNotNone(request.confirmation_sent_at)
        self.assertIsNotNone(request.position_one_sent_at)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(len(mail.outbox[0].attachments), 1)

        request.status = VideoRequest.Status.READY
        request.video_external_id = "readyVideoId"
        request.video_ready_at = timezone.now()
        request.save()
        self.assertEqual(deliver_video_request_notifications.run(), 1)
        request.refresh_from_db()
        self.assertIsNotNone(request.ready_notification_sent_at)
        self.assertEqual(len(mail.outbox), 3)
        self.assertNotIn("readyVideoId", mail.outbox[-1].body)

    def test_expired_unpaid_request_removes_private_documents(self):
        document = SimpleUploadedFile(
            "assignment.pdf",
            b"%PDF-1.4\nsynthetic\n%%EOF",
            content_type="application/pdf",
        )
        request = VideoRequest.objects.get(
            reference=self.create_checkout(key="video-expire-001", documents=[document]).request_reference
        )
        stored_path = request.documents.get().storage_path
        VideoRequest.objects.filter(pk=request.pk).update(payment_expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(expire_unpaid_video_requests.run(), 1)
        request.refresh_from_db()
        self.assertEqual(request.status, VideoRequest.Status.CANCELLED)
        self.assertFalse(VideoRequestDocument.objects.filter(request=request).exists())
        self.assertFalse(Path(self.storage_directory.name, stored_path).exists())

    def test_cleanup_rechecks_payment_before_deleting_private_documents(self):
        document = SimpleUploadedFile("paper.pdf", b"%PDF-1.4\nsynthetic\n%%EOF", content_type="application/pdf")
        request = VideoRequest.objects.get(
            reference=self.create_checkout(key="video-expire-race-001", documents=[document]).request_reference
        )
        stored_path = request.documents.get().storage_path
        VideoRequest.objects.filter(pk=request.pk).update(payment_expires_at=timezone.now() - timedelta(seconds=1))
        stale_candidate = VideoRequest.objects.get(pk=request.pk)
        self.pay(request)
        self.assertEqual(request.status, VideoRequest.Status.PAYMENT_REVIEW)

        with patch("content.tasks.VideoRequest.objects.filter") as candidates:
            candidates.return_value.prefetch_related.return_value.__getitem__.return_value = [stale_candidate]
            self.assertEqual(expire_unpaid_video_requests.run(), 0)

        self.assertTrue(request.documents.exists())
        self.assertTrue(Path(self.storage_directory.name, stored_path).exists())

    def test_cleanup_retains_metadata_for_retry_after_storage_failure(self):
        document = SimpleUploadedFile("paper.pdf", b"%PDF-1.4\nsynthetic\n%%EOF", content_type="application/pdf")
        request = VideoRequest.objects.get(
            reference=self.create_checkout(key="video-expire-retry-001", documents=[document]).request_reference
        )
        stored_path = request.documents.get().storage_path
        VideoRequest.objects.filter(pk=request.pk).update(payment_expires_at=timezone.now() - timedelta(seconds=1))

        with patch("django.core.files.storage.FileSystemStorage.delete", side_effect=OSError("Storage unavailable")):
            with self.assertRaises(OSError):
                expire_unpaid_video_requests.run()

        request.refresh_from_db()
        self.assertEqual(request.status, VideoRequest.Status.PENDING_PAYMENT)
        self.assertTrue(request.documents.exists())
        self.assertTrue(Path(self.storage_directory.name, stored_path).exists())
        self.assertEqual(expire_unpaid_video_requests.run(), 1)
        self.assertFalse(request.documents.exists())
        self.assertFalse(Path(self.storage_directory.name, stored_path).exists())
