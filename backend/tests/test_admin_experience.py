"""Regression checks for the accessible, private Amaris admin experience."""

from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.contrib import admin
from django.contrib.staticfiles.finders import find
from django.test import SimpleTestCase

from content.models import (
    Announcement,
    AnnouncementMedia,
    ContactEnquiry,
    Course,
    Enrollment,
    LiveClassBooking,
    Payment,
    StudentRecord,
    VideoRequest,
)
from content.tutor_finance_admin import TutorPaymentProfileAdmin
from content.tutor_finance_models import TutorPaymentProfile


class AdminExperienceTests(SimpleTestCase):
    def test_jazzmin_assets_are_collected_from_installed_content_app(self):
        css_path = settings.JAZZMIN_SETTINGS["custom_css"]
        js_path = settings.JAZZMIN_SETTINGS["custom_js"]
        self.assertEqual(css_path, "content/admin/amaris-admin.css")
        self.assertEqual(js_path, "content/admin/amaris-admin.js")
        self.assertTrue(find(css_path))
        self.assertTrue(find(js_path))

    def test_animation_respects_reduced_motion_and_form_actions_remain_native(self):
        css = Path(find(settings.JAZZMIN_SETTINGS["custom_css"])).read_text(encoding="utf-8")
        js = Path(find(settings.JAZZMIN_SETTINGS["custom_js"])).read_text(encoding="utf-8")
        self.assertIn("prefers-reduced-motion: reduce", css)
        self.assertIn("focus-visible", css)
        self.assertIn("@media (max-width: 767px)", css)
        self.assertIn('aria-live", "polite"', js)
        self.assertIn("form.checkValidity()", js)
        self.assertNotIn(".preventDefault(", js)
        self.assertNotIn(".disabled = true", js)
        self.assertNotIn("fetch(", js)

    def test_index_shortcuts_are_guarded_by_permissions(self):
        template = settings.BASE_DIR / "templates" / "admin" / "amaris_index.html"
        content = template.read_text(encoding="utf-8")
        self.assertIn("perms.content.view_course", content)
        self.assertIn("perms.content.view_contactenquiry", content)
        self.assertIn("perms.content.view_tutorapplication", content)
        self.assertIn("request.user.is_superuser", content)

    def test_high_volume_admins_disable_extra_full_count(self):
        for model in (Course, StudentRecord, Enrollment, Payment, ContactEnquiry, LiveClassBooking, VideoRequest):
            with self.subTest(model=model.__name__):
                self.assertFalse(admin.site._registry[model].show_full_result_count)

    def test_related_rows_are_loaded_with_the_list_not_per_row(self):
        expected = {
            AnnouncementMedia: ("announcement",),
            Enrollment: ("student", "course"),
            Payment: ("student", "course"),
            LiveClassBooking: ("student", "slot"),
            VideoRequest: ("student", "assigned_tutor"),
        }
        for model, relationships in expected.items():
            with self.subTest(model=model.__name__):
                self.assertEqual(admin.site._registry[model].list_select_related, relationships)

    def test_private_marketing_and_bank_account_admin_permissions_unchanged(self):
        ordinary_staff = SimpleNamespace(is_active=True, is_staff=True, is_superuser=False)
        superuser = SimpleNamespace(is_active=True, is_staff=True, is_superuser=True)
        request = SimpleNamespace(user=ordinary_staff)

        self.assertFalse(admin.site._registry[Announcement].has_view_permission(request))
        self.assertFalse(admin.site._registry[AnnouncementMedia].has_view_permission(request))
        bank = admin.site._registry[TutorPaymentProfile]
        self.assertIsInstance(bank, TutorPaymentProfileAdmin)
        self.assertFalse(bank.has_view_permission(request))
        request.user = superuser
        self.assertTrue(admin.site._registry[Announcement].has_view_permission(request))
        self.assertTrue(bank.has_view_permission(request))
        self.assertFalse(bank.has_delete_permission(request))
