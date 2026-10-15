from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase, override_settings
from django.contrib.admin.sites import AdminSite

from content.admin import AnnouncementAdmin
from content.models import Announcement
from marketing.models import AnnouncementMedia


class MarketingPermissionTests(TestCase):
    def test_only_superuser_can_manage_announcements(self):
        User = get_user_model()
        staff = User.objects.create_user("editor", password="test", is_staff=True)
        superuser = User.objects.create_superuser("owner", "owner@example.org", "test")
        model_admin = AnnouncementAdmin(Announcement, AdminSite())
        for user, expected in [(staff, False), (superuser, True)]:
            request = RequestFactory().get("/admin/content/announcement/")
            request.user = user
            self.assertEqual(model_admin.has_module_permission(request), expected)
            self.assertEqual(model_admin.has_view_permission(request), expected)
            self.assertEqual(model_admin.has_add_permission(request), expected)
            self.assertEqual(model_admin.has_change_permission(request), expected)
            self.assertEqual(model_admin.has_delete_permission(request), expected)

    @override_settings(DEBUG=True)
    def test_rejects_disguised_pdf(self):
        announcement = Announcement.objects.create(title="Campaign", message="Launch")
        asset = AnnouncementMedia(
            announcement=announcement,
            media_type="pdf",
            file=SimpleUploadedFile("claim.pdf", b"not a pdf"),
        )
        with self.assertRaises(ValidationError):
            asset.full_clean()

    @override_settings(DEBUG=True)
    def test_accepts_valid_pdf_header(self):
        announcement = Announcement.objects.create(title="Campaign", message="Launch")
        asset = AnnouncementMedia(
            announcement=announcement,
            media_type="pdf",
            file=SimpleUploadedFile("brochure.pdf", b"%PDF-1.7\ncontent"),
        )
        asset.full_clean()
