from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from content.models import Announcement, AnnouncementMedia


class MarketingMediaTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser("marketing_super", "super@example.test", "temporary-test-password")
        self.staff = User.objects.create_user(
            "marketing_staff", "staff@example.test", "temporary-test-password", is_staff=True
        )
        self.announcement = Announcement.objects.create(
            title="New exam preparation", message="Enrol now", is_published=True
        )

    def test_staff_cannot_access_marketing_admin(self):
        self.client.force_login(self.staff)
        urls = [
            reverse("admin:content_announcement_changelist"),
            reverse("admin:content_announcement_add"),
            reverse("admin:content_announcementmedia_changelist"),
            reverse("admin:content_announcementmedia_add"),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url, secure=True).status_code, 403)

    def test_superuser_can_access_media_admin(self):
        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get(reverse("admin:content_announcementmedia_changelist"), secure=True).status_code, 200
        )

    def test_reject_disguised_executable_pdf(self):
        obj = AnnouncementMedia(announcement=self.announcement, kind="pdf", title="Fake PDF")
        obj.file = SimpleUploadedFile("unsafe.pdf", b"<script>alert('x')</script>")
        with self.assertRaises(ValidationError):
            obj.full_clean()

    def test_accept_valid_pdf(self):
        obj = AnnouncementMedia(announcement=self.announcement, kind="pdf", title="Real PDF")
        obj.file = SimpleUploadedFile("guide.pdf", b"%PDF-1.7\n")
        obj.full_clean()

    def test_unpublished_media_not_public(self):
        self.announcement.is_published = False
        self.announcement.save()
        # Use unsaved dummy file path to avoid touching S3 in this test.
        obj = AnnouncementMedia.objects.create(
            announcement=self.announcement, kind="pdf", title="Private", file="marketing/announcements/guide.pdf"
        )
        self.assertEqual(
            self.client.get(reverse("public-marketing-media", args=[obj.pk]), secure=True).status_code, 404
        )

    @override_settings(CMS_STORAGE_BUCKET_NAME="")
    def test_public_media_fails_closed_without_s3(self):
        obj = AnnouncementMedia.objects.create(
            announcement=self.announcement, kind="pdf", title="No storage", file="marketing/announcements/guide.pdf"
        )
        self.assertEqual(
            self.client.get(reverse("public-marketing-media", args=[obj.pk]), secure=True).status_code, 404
        )

    @override_settings(
        CMS_STORAGE_BUCKET_NAME="amaris-cms-files",
        AWS_S3_ENDPOINT_URL="https://example.supabase.co/storage/v1/s3",
    )
    def test_signed_media_redirect_for_published_announcement(self):
        obj = AnnouncementMedia.objects.create(
            announcement=self.announcement,
            kind="pdf",
            title="Public guide",
            file="marketing/announcements/public-guide.pdf",
        )
        signed_url = "https://example.supabase.co/storage/v1/s3/amaris-cms-files/public-guide.pdf?X-Amz-Signature=fake"
        with patch.object(obj.file.storage, "url", return_value=signed_url):
            response = self.client.get(reverse("public-marketing-media", args=[obj.pk]), secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], signed_url)
        self.assertIn("no-store", response["Cache-Control"])

    def test_anonymous_cannot_edit_marketing_admin(self):
        self.assertEqual(
            self.client.get(reverse("admin:content_announcementmedia_add"), secure=True).status_code,
            302,
        )

    def test_reject_file_over_supabase_bucket_limit(self):
        file = SimpleUploadedFile("oversize.pdf", b"%PDF-1.7\n")
        file.size = 50 * 1024 * 1024 + 1
        obj = AnnouncementMedia(announcement=self.announcement, kind="pdf", title="Oversize")
        obj.file = file
        with self.assertRaisesMessage(ValidationError, "Maximum file size is 50 MB"):
            obj.full_clean()

    def test_reject_non_video_file_disguised_as_mp4(self):
        obj = AnnouncementMedia(announcement=self.announcement, kind="video", title="Invalid video")
        obj.file = SimpleUploadedFile("advert.mp4", b"<html>not a video</html>")
        with self.assertRaisesMessage(ValidationError, "File content does not match"):
            obj.full_clean()

    def test_staff_post_cannot_create_change_or_delete_media(self):
        asset = AnnouncementMedia.objects.create(
            announcement=self.announcement,
            kind="pdf",
            title="Existing",
            file="marketing/announcements/existing.pdf",
        )
        self.client.force_login(self.staff)
        attempts = (
            (
                reverse("admin:content_announcementmedia_add"),
                {"announcement": self.announcement.pk, "title": "Injected", "kind": "pdf", "order": 0},
            ),
            (
                reverse("admin:content_announcementmedia_change", args=[asset.pk]),
                {"announcement": self.announcement.pk, "title": "Injected", "kind": "pdf", "order": 0},
            ),
            (reverse("admin:content_announcementmedia_delete", args=[asset.pk]), {"post": "yes"}),
        )
        for url, data in attempts:
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url, data, secure=True).status_code, 403)
        asset.refresh_from_db()
        self.assertEqual(asset.title, "Existing")
        self.assertEqual(AnnouncementMedia.objects.count(), 1)

    def test_superuser_can_create_change_and_delete_pdf(self):
        self.client.force_login(self.admin)
        with TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                add = self.client.post(
                    reverse("admin:content_announcementmedia_add"),
                    {
                        "announcement": self.announcement.pk,
                        "kind": "pdf",
                        "title": "Marketing guide",
                        "order": 1,
                        "file": SimpleUploadedFile(
                            "marketing-guide.pdf", b"%PDF-1.7\n", content_type="application/pdf"
                        ),
                        "_save": "Save",
                    },
                    secure=True,
                )
                self.assertEqual(add.status_code, 302)
                asset = AnnouncementMedia.objects.get(title="Marketing guide")
                change = self.client.post(
                    reverse("admin:content_announcementmedia_change", args=[asset.pk]),
                    {
                        "announcement": self.announcement.pk,
                        "kind": "pdf",
                        "title": "Updated guide",
                        "order": 2,
                        "_save": "Save",
                    },
                    secure=True,
                )
                self.assertEqual(change.status_code, 302)
                asset.refresh_from_db()
                self.assertEqual(asset.title, "Updated guide")
                delete = self.client.post(
                    reverse("admin:content_announcementmedia_delete", args=[asset.pk]),
                    {"post": "yes"},
                    secure=True,
                )
                self.assertEqual(delete.status_code, 302)
                self.assertFalse(AnnouncementMedia.objects.filter(pk=asset.pk).exists())
