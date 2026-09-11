from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from content.admin import CourseAdmin, SiteSettingsAdmin, StudentRecordAdmin
from content.models import Course, CourseCategory, SiteSettings, StudentRecord
from content.rbac import (
    ROLE_ADMINISTRATOR,
    ROLE_STUDENT,
    ROLE_SUPER_ADMINISTRATOR,
    ROLE_TUTOR,
    assign_role,
    ensure_role_groups,
    user_has_role,
)


class RBACTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()
        cls.student = get_user_model().objects.create_user("student", password="StrongPass123!")
        cls.tutor = get_user_model().objects.create_user("tutor", password="StrongPass123!")
        cls.admin_user = get_user_model().objects.create_user("administrator", password="StrongPass123!")
        cls.super_admin = get_user_model().objects.create_superuser(
            "superadmin", "superadmin@example.com", "StrongPass123!"
        )
        assign_role(cls.student, ROLE_STUDENT)
        assign_role(cls.tutor, ROLE_TUTOR)
        assign_role(cls.admin_user, ROLE_ADMINISTRATOR)
        assign_role(cls.super_admin, ROLE_SUPER_ADMINISTRATOR)

    def test_roles_are_explicit_and_exclusive(self):
        self.assertTrue(user_has_role(self.student, ROLE_STUDENT))
        self.assertTrue(user_has_role(self.tutor, ROLE_TUTOR))
        self.assertTrue(user_has_role(self.admin_user, ROLE_ADMINISTRATOR))
        self.assertTrue(user_has_role(self.super_admin, ROLE_SUPER_ADMINISTRATOR))
        self.assertFalse(user_has_role(self.admin_user, ROLE_SUPER_ADMINISTRATOR))
        self.assertFalse(self.admin_user.is_superuser)

    def test_student_cannot_access_django_admin(self):
        self.client.force_login(self.student)
        response = self.client.get("/admin/", secure=True)
        self.assertEqual(response.status_code, 302)

    def test_tutor_can_access_django_admin(self):
        self.client.force_login(self.tutor)
        response = self.client.get("/admin/", secure=True)
        self.assertEqual(response.status_code, 200)

    def test_tutor_has_course_upload_permissions_but_not_system_settings(self):
        self.assertTrue(self.tutor.has_perm("content.add_course"))
        self.assertTrue(self.tutor.has_perm("content.change_course"))
        self.assertTrue(self.tutor.has_perm("content.view_course"))
        self.assertFalse(self.tutor.has_perm("content.delete_course"))
        self.assertFalse(self.tutor.has_perm("content.change_sitesettings"))
        self.assertFalse(self.tutor.has_perm("content.view_studentrecord"))

    def test_administrator_is_not_superuser(self):
        self.assertTrue(self.admin_user.is_staff)
        self.assertFalse(self.admin_user.is_superuser)


class TutorAdminBoundaryTests(TestCase):
    def setUp(self):
        ensure_role_groups()
        self.tutor = get_user_model().objects.create_user("tutor2", password="StrongPass123!")
        assign_role(self.tutor, ROLE_TUTOR)
        self.factory = RequestFactory()
        self.request = self.factory.get("/admin/")
        self.request.user = self.tutor
        self.category = CourseCategory.objects.create(name="CAPS", slug="caps-rbac")

    def test_tutor_course_admin_allows_add_and_change(self):
        model_admin = CourseAdmin(Course, admin.site)
        self.assertTrue(model_admin.has_add_permission(self.request))
        self.assertTrue(model_admin.has_change_permission(self.request))

    def test_tutor_cannot_modify_site_settings(self):
        SiteSettings.objects.create()
        model_admin = SiteSettingsAdmin(SiteSettings, admin.site)
        self.assertFalse(model_admin.has_change_permission(self.request))

    def test_tutor_cannot_view_student_records(self):
        model_admin = StudentRecordAdmin(StudentRecord, admin.site)
        self.assertFalse(model_admin.has_view_permission(self.request))
