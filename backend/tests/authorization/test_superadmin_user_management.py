from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from content.admin_users import SuperAdminUserAdmin, SuperAdminUserCreationForm
from content.rbac import (
    ROLE_STUDENT,
    ROLE_SUPER_ADMINISTRATOR,
    ROLE_TUTOR,
    assign_role,
    user_has_role,
)

User = get_user_model()


class SuperAdminUserManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.super_admin = User.objects.create_superuser(
            username="superadmin-manager",
            email="superadmin-manager@example.com",
            password="StrongPass123!",
        )
        assign_role(cls.super_admin, ROLE_SUPER_ADMINISTRATOR)

        cls.tutor = User.objects.create_user(
            username="existing-tutor",
            email="existing-tutor@example.com",
            password="StrongPass123!",
        )
        assign_role(cls.tutor, ROLE_TUTOR)

    def test_super_admin_can_open_user_add_page(self):
        self.client.force_login(self.super_admin)
        response = self.client.get("/admin/auth/user/add/", secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tutor")
        self.assertContains(response, "Student")

    def test_tutor_cannot_open_user_management(self):
        self.client.force_login(self.tutor)
        response = self.client.get("/admin/auth/user/", secure=True)
        self.assertIn(response.status_code, (302, 403))

    def test_super_admin_can_create_tutor_with_hashed_password(self):
        form = SuperAdminUserCreationForm(
            data={
                "username": "new-tutor",
                "email": "new-tutor@example.com",
                "first_name": "New",
                "last_name": "Tutor",
                "role": ROLE_TUTOR,
                "password1": "VeryStrongTutorPass123!",
                "password2": "VeryStrongTutorPass123!",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()

        self.assertTrue(user_has_role(user, ROLE_TUTOR))
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password("VeryStrongTutorPass123!"))
        self.assertNotEqual(user.password, "VeryStrongTutorPass123!")

    def test_super_admin_can_create_student_with_hashed_password(self):
        form = SuperAdminUserCreationForm(
            data={
                "username": "new-student",
                "email": "new-student@example.com",
                "first_name": "New",
                "last_name": "Student",
                "role": ROLE_STUDENT,
                "password1": "VeryStrongStudentPass123!",
                "password2": "VeryStrongStudentPass123!",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()

        self.assertTrue(user_has_role(user, ROLE_STUDENT))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password("VeryStrongStudentPass123!"))

    def test_only_super_admin_can_manage_users_in_admin_class(self):
        factory = RequestFactory()
        model_admin = SuperAdminUserAdmin(User, admin.site)

        super_request = factory.get("/admin/auth/user/")
        super_request.user = self.super_admin
        self.assertTrue(model_admin.has_view_permission(super_request))
        self.assertTrue(model_admin.has_add_permission(super_request))

        tutor_request = factory.get("/admin/auth/user/")
        tutor_request.user = self.tutor
        self.assertFalse(model_admin.has_view_permission(tutor_request))
        self.assertFalse(model_admin.has_add_permission(tutor_request))
