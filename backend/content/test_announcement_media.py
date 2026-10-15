from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
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
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_superuser_can_access_media_admin(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("admin:content_announcementmedia_changelist")).status_code, 200)

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
        self.assertEqual(self.client.get(reverse("public-marketing-media", args=[obj.pk])).status_code, 404)

    @override_settings(CMS_STORAGE_BUCKET_NAME="")
    def test_public_media_fails_closed_without_s3(self):
        obj = AnnouncementMedia.objects.create(
            announcement=self.announcement, kind="pdf", title="No storage", file="marketing/announcements/guide.pdf"
        )
        self.assertEqual(self.client.get(reverse("public-marketing-media", args=[obj.pk])).status_code, 404)
