import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from smtplib import SMTPConnectError
from threading import Barrier
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.core.files.storage import InMemoryStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.mail import EmailMultiAlternatives
from django.db import OperationalError, close_old_connections, connection, transaction
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from content.admin import VideoAssetAdmin
from content.authentication import SupabaseStudentAuthentication
from content.models import SiteSettings, VideoAsset
from content.services.branded_email import apply_letterhead
from content.services.tutor_video_uploads import UploadConflict, deliver_alert, submit_video
from content.tutor_video_models import TutorVideoUpload
from content.tutor_video_tasks import deliver_tutor_video_admin_alerts


class VideoFixtures:
    def setUp(self):
        caches["default"].clear()
        self.tutor = get_user_model().objects.create_user(
            username="upload-tutor", email="tutor@example.test", first_name="Tutor", last_name="Example"
        )
        self.tutor.groups.add(Group.objects.get_or_create(name="Tutors")[0])
        SiteSettings.objects.create(email="admin@example.test")
        self.storage = InMemoryStorage()
        self.storage_patch = patch.object(VideoAsset._meta.get_field("source_file"), "storage", self.storage)
        self.storage_patch.start()
        self.addCleanup(self.storage_patch.stop)
        self.metadata = {
            "title": "Quadratic equations",
            "curriculum": "caps",
            "subject": "mathematics",
            "academic_level": "Grade 11",
            "topic": "Factorisation",
            "duration_seconds": 1200,
        }
        self.api = APIClient(HTTP_X_FORWARDED_PROTO="https")
        self.api.force_authenticate(user=self.tutor)

    def video_file(self, data=b"synthetic-video", name="lesson.mp4"):
        return SimpleUploadedFile(name, b"\x00\x00\x00\x18ftypisom" + data, content_type="video/mp4")

    def upload(self, key="synthetic-upload-key", **kwargs):
        return submit_video(tutor=self.tutor, key=key, upload=self.video_file(), metadata=self.metadata, **kwargs)


@override_settings(
    TUTOR_VIDEO_UPLOADS_ENABLED=True,
    TUTOR_VIDEO_MAX_UPLOAD_BYTES=104857600,
    TUTOR_VIDEO_ADMIN_EMAIL="",
    PUBLIC_API_URL="https://api.example.test",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class TutorVideoUploadTests(VideoFixtures, TestCase):
    def test_private_draft_upload_and_detailed_letterhead_email_to_admin_once(self):
        event, created = self.upload()
        self.assertTrue(created)
        self.assertFalse(event.video.is_published)
        self.assertFalse(event.video.allow_preview)
        self.assertEqual(event.video.uploaded_by, self.tutor)
        self.assertTrue(self.storage.exists(event.video.source_file.name))
        self.assertEqual(deliver_tutor_video_admin_alerts(), 1)
        self.assertEqual(deliver_tutor_video_admin_alerts(), 0)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["admin@example.test"])
        self.assertEqual(message.cc, [])
        self.assertEqual(message.bcc, [])
        for value in [
            "Tutor Example",
            "tutor@example.test",
            "Quadratic equations",
            "CAPS",
            "Grade 11",
            "Factorisation",
            "SAST (UTC+2)",
            "lesson.mp4",
            "1200 seconds",
            "Draft / pending Admin review",
        ]:
            self.assertIn(value, message.body)
        self.assertNotIn(event.video.source_file.name, message.body)
        self.assertIn(f"/admin/content/videoasset/{event.video_id}/change/", message.body)
        html = message.alternatives[0][0]
        for value in [
            "Official academy communication",
            "Bethuel Moukangwe",
            "27 Tshivhase Street",
            "071 415 6665",
            "cid:amaris-letterhead-logo",
        ]:
            self.assertIn(value, html)
        self.assertEqual(message.attachments[0].get("Content-Disposition").split(";")[0], "inline")

    def test_idempotent_retry_and_changed_payload_rejected(self):
        first, _ = self.upload()
        again, created = self.upload()
        self.assertEqual(first.pk, again.pk)
        self.assertFalse(created)
        self.assertEqual(VideoAsset.objects.count(), 1)
        self.metadata["title"] = "Different title"
        with self.assertRaises(UploadConflict):
            self.upload()
        self.assertEqual(TutorVideoUpload.objects.count(), 1)

    def test_replacement_is_owned_unpublished_and_metadata_changes_do_not_alert(self):
        event, _ = self.upload()
        video = event.video
        video.title = "Edited title"
        video.save()
        self.assertEqual(TutorVideoUpload.objects.count(), 1)
        replacement, _ = self.upload(key="replace-video-key", video_id=video.pk)
        self.assertEqual(replacement.video_id, video.pk)
        video.is_published = True
        video.save()
        with self.assertRaises(UploadConflict):
            self.upload(key="published-video-key", video_id=video.pk)
        other = get_user_model().objects.create_user(username="other-tutor")
        video.uploaded_by, video.is_published = other, False
        video.save()
        with self.assertRaises(UploadConflict):
            self.upload(key="stolen-video-key", video_id=video.pk)

    def test_failed_database_transaction_never_creates_a_deliverable_alert(self):
        with self.assertRaises(RuntimeError), transaction.atomic():
            self.upload()
            raise RuntimeError("synthetic rollback")
        self.assertFalse(TutorVideoUpload.objects.exists())
        self.assertEqual(deliver_tutor_video_admin_alerts(), 0)

    def test_real_multipart_api_forces_owner_and_draft_and_returns_no_storage_key(self):
        response = self.api.post(
            reverse("tutor-videos"),
            {
                **self.metadata,
                "source_file": self.video_file(),
                "idempotency_key": "real-multipart-key",
                "uploaded_by": 999,
                "is_published": True,
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        video = VideoAsset.objects.get()
        self.assertEqual(video.uploaded_by, self.tutor)
        self.assertFalse(video.is_published)
        self.assertNotIn(video.source_file.name, str(response.data))
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_anonymous_student_and_unapproved_tutor_cannot_upload(self):
        client = APIClient(HTTP_X_FORWARDED_PROTO="https")
        self.assertEqual(client.post(reverse("tutor-videos")).status_code, 401)
        payload = {"id": str(uuid.uuid4()), "email": "student@example.test", "email_confirmed_at": "2026-01-01"}
        with patch.object(SupabaseStudentAuthentication, "_validate_token", return_value=payload):
            self.assertEqual(client.post(reverse("tutor-videos"), HTTP_AUTHORIZATION="Bearer student").status_code, 401)
        self.tutor.groups.clear()
        with self.assertRaises(ValidationError):
            self.upload()

    def test_unsupported_or_oversize_files_and_multiple_parts_rejected(self):
        with self.assertRaises(ValidationError):
            submit_video(
                tutor=self.tutor,
                key="bad-video-key",
                upload=SimpleUploadedFile("fake.mp4", b"<script>bad</script>", content_type="video/mp4"),
                metadata=self.metadata,
            )
        with override_settings(TUTOR_VIDEO_MAX_UPLOAD_BYTES=4):
            response = self.api.post(
                reverse("tutor-videos"),
                {**self.metadata, "source_file": self.video_file(), "idempotency_key": "too-large-key"},
                format="multipart",
            )
            self.assertEqual(response.status_code, 413)
        self.assertFalse(VideoAsset.objects.exists())

    def test_storage_failure_does_not_commit_video_or_alert(self):
        with patch.object(self.storage, "save", side_effect=OSError("synthetic failure")):
            with self.assertRaises(OSError):
                self.upload()
        self.assertFalse(VideoAsset.objects.exists())
        self.assertFalse(TutorVideoUpload.objects.exists())

    def test_rejected_smtp_retries_with_backoff_and_changed_admin_is_held(self):
        event, _ = self.upload()
        with patch(
            "content.services.tutor_video_uploads.EmailMultiAlternatives.send",
            side_effect=SMTPConnectError(421, b"not accepted"),
        ) as send:
            self.assertEqual(deliver_alert(event.pk), 0)
            self.assertEqual(deliver_alert(event.pk), 0)
            self.assertEqual(send.call_count, 1)
        event.refresh_from_db()
        self.assertEqual(event.delivery_status, "queued")
        self.assertGreater(event.next_attempt_at, timezone.now())
        event.next_attempt_at = timezone.now() - timedelta(seconds=1)
        event.save()
        SiteSettings.objects.filter(pk=1).update(email="new-admin@example.test")
        self.assertEqual(deliver_alert(event.pk), 0)
        event.refresh_from_db()
        self.assertEqual(event.error_code, "admin_recipient_changed")

    def test_multiple_file_parts_do_not_create_a_video(self):
        response = self.api.post(
            reverse("tutor-videos"),
            {
                **self.metadata,
                "source_file": [self.video_file(), self.video_file()],
                "idempotency_key": "multi-file-key",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(VideoAsset.objects.exists())

    def test_unknown_smtp_outcome_and_crash_after_acceptance_are_not_blindly_retried(self):
        event, _ = self.upload()
        with patch(
            "content.services.tutor_video_uploads.EmailMultiAlternatives.send", side_effect=TimeoutError
        ) as send:
            self.assertEqual(deliver_alert(event.pk), 0)
            self.assertEqual(deliver_tutor_video_admin_alerts(), 0)
            self.assertEqual(send.call_count, 1)
        event.refresh_from_db()
        self.assertEqual(event.delivery_status, "review")
        event.delivery_status = "queued"
        event.save()
        with patch("content.services.tutor_video_uploads.TutorVideoUpload.objects.filter") as query:
            query.return_value.update.side_effect = OperationalError("simulated commit failure")
            with self.assertRaises(OperationalError):
                deliver_alert(event.pk)
        event.refresh_from_db()
        self.assertEqual(event.delivery_status, "sending")
        self.assertEqual(deliver_alert(event.pk), 0)
        event.sending_at = timezone.now() - timedelta(hours=2)
        event.save()
        deliver_tutor_video_admin_alerts()
        event.refresh_from_db()
        self.assertEqual(event.delivery_status, "review")

    def test_letterhead_preserves_original_text_headers_and_pdf_and_escapes_html(self):
        message = EmailMultiAlternatives(
            subject="Test", body="Original body", to=["admin@example.test"], headers={"X-Test": "kept"}
        )
        message.attach("invoice.pdf", b"%PDF-synthetic", "application/pdf")
        apply_letterhead(message, "<script>heading</script>", ["<img src=x onerror=bad>"])
        apply_letterhead(message, "<script>heading</script>", ["<img src=x onerror=bad>"])
        self.assertEqual(message.body, "Original body")
        self.assertEqual(message.attachments[0][1], b"%PDF-synthetic")
        self.assertEqual(len(message.attachments), 2)
        self.assertEqual(len(message.alternatives), 1)
        self.assertNotIn("<script>", message.alternatives[0][0])
        self.assertIn("&lt;img", message.alternatives[0][0])
        self.assertEqual(message.extra_headers["X-Test"], "kept")

    def test_django_admin_tutor_upload_alerts_but_metadata_edit_does_not(self):
        request = RequestFactory().post("/admin/content/videoasset/add/")
        request.user = self.tutor
        manager = VideoAssetAdmin(VideoAsset, admin.site)
        video = VideoAsset(provider="s3", source_file=self.video_file(), **self.metadata)
        manager.save_model(request, video, SimpleNamespace(changed_data=["source_file"]), False)
        self.assertEqual(TutorVideoUpload.objects.count(), 1)
        self.assertEqual(video.uploaded_by, self.tutor)
        video.title = "Updated title"
        manager.save_model(request, video, SimpleNamespace(changed_data=["title"]), True)
        self.assertEqual(TutorVideoUpload.objects.count(), 1)
        self.assertNotIn("publish_selected", manager.get_actions(request))


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row locking/RLS required")
@override_settings(
    TUTOR_VIDEO_MAX_UPLOAD_BYTES=104857600,
    TUTOR_VIDEO_ADMIN_EMAIL="",
    PUBLIC_API_URL="https://api.example.test",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class TutorVideoConcurrencyTests(VideoFixtures, TransactionTestCase):
    def test_concurrent_workers_send_one_alert_and_table_is_private(self):
        event, _ = self.upload()
        barrier = Barrier(2)

        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return deliver_alert(event.pk)
            finally:
                close_old_connections()

        with patch("content.services.tutor_video_uploads.EmailMultiAlternatives.send", return_value=1) as send:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: worker(), range(2)))
        self.assertEqual(sorted(results), [0, 1])
        self.assertEqual(send.call_count, 1)
        with connection.cursor() as cursor:
            cursor.execute("SELECT relrowsecurity FROM pg_class WHERE relname = 'content_tutorvideoupload'")
            self.assertTrue(cursor.fetchone()[0])
