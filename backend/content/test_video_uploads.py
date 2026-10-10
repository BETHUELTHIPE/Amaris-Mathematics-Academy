"""No real S3 credentials, uploads, payments, or student data in these tests."""
import uuid
from decimal import Decimal
from unittest.mock import Mock, patch

from django.test import TestCase
from django.urls import reverse
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from content.authentication import SupabaseStudentPrincipal
from content.models import StudentRecord, VideoRequest, VideoRequestDocument
from content.video_uploads import (
    MAX_REQUEST_BYTES,
    PART_BYTES,
    _owned_key,
    begin_upload,
    complete_upload,
    part_url,
    validate_file,
)


class VideoUploadTests(TestCase):
    def setUp(self):
        self.student = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(),
            email="private-uploader@example.test",
            first_name="Synthetic",
            last_name="Student",
        )
        self.other = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(),
            email="other-uploader@example.test",
            first_name="Other",
            last_name="Synthetic",
        )
        self.item = VideoRequest.objects.create(
            student=self.student,
            reference="VRQ-test-large-upload",
            idempotency_key="test-large-upload",
            programme="caps",
            subject="mathematics",
            level="Grade 12",
            topic="Calculus",
            request_type="chapter_topic",
            amount=Decimal("450.00"),
        )
        self.s3 = Mock()
        self.s3.create_multipart_upload.return_value = {"UploadId": "upload123"}
        self.s3.generate_presigned_url.return_value = "https://storage.example.test/signed"
        self.s3.head_object.return_value = {
            "ContentLength": 16,
            "ContentType": "application/pdf",
        }
        self.bucket = "private-student-data"

    def test_file_and_folder_budget_and_rejected_file_types(self):
        name, size, mime, extension = validate_file(
            "Exam papers/2026/questions.pdf", MAX_REQUEST_BYTES, "application/pdf"
        )
        self.assertEqual((name, size, mime, extension), (
            "Exam papers/2026/questions.pdf", MAX_REQUEST_BYTES, "application/pdf", ".pdf"
        ))
        for name in ("../secrets.pdf", "folder/../../secrets.pdf", "/absolute.pdf", "a//b.pdf"):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                validate_file(name, 10, "application/pdf")
        for name, mime in (("evil.exe", "application/octet-stream"), ("test.pdf", "image/png")):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                validate_file(name, 10, mime)
        for size in (0, MAX_REQUEST_BYTES + 1):
            with self.assertRaises(ValidationError):
                validate_file("large.zip", size, "application/zip")

    @patch("content.video_uploads._client")
    def test_private_multipart_key_and_signed_part(self, client_mock):
        client_mock.return_value = (self.s3, self.bucket)
        init = begin_upload(self.student, self.item.reference, {
            "name": "School work/paper.pdf",
            "size": 16,
            "content_type": "application/pdf",
        })
        self.assertTrue(init["key"].startswith(
            f"{self.student.supabase_user_id}/video-requests/{self.item.pk}/documents/"
        ))
        self.assertEqual(init["part_bytes"], PART_BYTES)
        self.assertEqual(init["parts"], 1)
        self.assertEqual(_owned_key(self.item, init["key"]), init["key"])
        with self.assertRaises(ValidationError):
            _owned_key(self.item, init["key"].replace(str(self.student.supabase_user_id), str(self.other.supabase_user_id)))
        signed = part_url(self.student, self.item.reference, {
            "key": init["key"], "upload_id": init["upload_id"], "part_number": 1
        })
        self.assertEqual(signed["url"], "https://storage.example.test/signed")
        self.assertEqual(self.s3.generate_presigned_url.call_args.kwargs["ExpiresIn"], 900)

    @patch("content.video_uploads._client")
    def test_complete_attaches_only_verified_private_object(self, client_mock):
        client_mock.return_value = (self.s3, self.bucket)
        init = begin_upload(self.student, self.item.reference, {
            "name": "Questions/paper.pdf", "size": 16, "content_type": "application/pdf"
        })
        values = {
            "name": "Questions/paper.pdf", "size": 16,
            "content_type": "application/pdf",
            "key": init["key"], "upload_id": init["upload_id"],
            "parts": [{"part_number": 1, "etag": '"1234567890abcdef"'}],
        }
        complete_upload(self.student, self.item.reference, values)
        attached = VideoRequestDocument.objects.get(request=self.item)
        self.assertEqual(attached.original_name, "Questions/paper.pdf")
        self.assertEqual(attached.size_bytes, 16)
        self.assertEqual(attached.sha256, "")
        self.assertEqual(attached.storage_path, init["key"])
        with self.assertRaises(ValidationError):
            complete_upload(self.student, self.item.reference, values)
        self.assertEqual(self.s3.complete_multipart_upload.call_count, 1)

    @patch("content.video_uploads._client")
    def test_bad_size_removes_completed_object_and_keeps_no_metadata(self, client_mock):
        client_mock.return_value = (self.s3, self.bucket)
        init = begin_upload(self.student, self.item.reference, {
            "name": "paper.pdf", "size": 16, "content_type": "application/pdf"
        })
        self.s3.head_object.return_value["ContentLength"] = 17
        with self.assertRaises(ValidationError):
            complete_upload(self.student, self.item.reference, {
                "name": "paper.pdf", "size": 16, "content_type": "application/pdf",
                "key": init["key"], "upload_id": init["upload_id"],
                "parts": [{"part_number": 1, "etag": "abcdef0123456789"}],
            })
        self.s3.delete_object.assert_called_once()
        self.assertFalse(self.item.documents.exists())

    @patch("content.video_uploads._client")
    def test_quota_rejected_before_creating_upload(self, client_mock):
        client_mock.return_value = (self.s3, self.bucket)
        VideoRequestDocument.objects.create(
            request=self.item, original_name="already.zip",
            storage_path="existing/private-file.zip", size_bytes=MAX_REQUEST_BYTES,
            content_type="application/zip", sha256="",
        )
        with self.assertRaises(ValidationError):
            begin_upload(self.student, self.item.reference, {
                "name": "more.pdf", "size": 1, "content_type": "application/pdf"
            })
        self.s3.create_multipart_upload.assert_not_called()

    @patch("content.video_uploads._client")
    def test_cannot_use_other_students_request_or_paid_request(self, client_mock):
        client_mock.return_value = (self.s3, self.bucket)
        with self.assertRaises(ValidationError):
            begin_upload(self.other, self.item.reference, {
                "name": "a.pdf", "size": 10, "content_type": "application/pdf"
            })
        VideoRequest.objects.filter(pk=self.item.pk).update(status=VideoRequest.Status.QUEUED)
        with self.assertRaises(ValidationError):
            begin_upload(self.student, self.item.reference, {
                "name": "a.pdf", "size": 10, "content_type": "application/pdf"
            })

    def test_feature_disabled_fails_closed_without_storage(self):
        with patch.dict("os.environ", {"VIDEO_REQUEST_LARGE_UPLOAD_ENABLED": "false"}):
            with self.assertRaises(ValidationError):
                begin_upload(self.student, self.item.reference, {
                    "name": "paper.pdf", "size": 16, "content_type": "application/pdf"
                })

    def test_endpoint_requires_authentication(self):
        response = APIClient().post(
            reverse("video-request-upload", args=[self.item.reference]),
            {"action": "init", "name": "paper.pdf", "size": 16, "content_type": "application/pdf"},
            format="json", secure=True,
        )
        self.assertIn(response.status_code, (401, 403))

    @patch("content.video_uploads._client")
    def test_endpoint_uses_authenticated_student_identity(self, client_mock):
        client_mock.return_value = (self.s3, self.bucket)
        client = APIClient()
        client.force_authenticate(user=SupabaseStudentPrincipal(
            student=self.other,
            supabase_user_id=str(self.other.supabase_user_id),
            email=self.other.email,
        ))
        response = client.post(
            reverse("video-request-upload", args=[self.item.reference]),
            {"action": "init", "name": "paper.pdf", "size": 16, "content_type": "application/pdf"},
            format="json", secure=True,
        )
        self.assertEqual(response.status_code, 400)
        self.s3.create_multipart_upload.assert_not_called()
