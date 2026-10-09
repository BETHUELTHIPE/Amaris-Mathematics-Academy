from __future__ import annotations

import uuid
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from content.authentication import SupabaseStudentAuthentication
from content.models import Course, CourseCategory, Payment, StudentRecord


class ProductionAuthenticationAuthorizationTests(APITestCase):
    def setUp(self):
        self.student = StudentRecord.objects.create(
            supabase_user_id=uuid.UUID("00000000-0000-4000-8000-000000000401"),
            email="auth.student@example.test",
            first_name="Auth",
            last_name="Student",
        )
        self.other_student = StudentRecord.objects.create(
            supabase_user_id=uuid.UUID("00000000-0000-4000-8000-000000000402"),
            email="other.auth.student@example.test",
            first_name="Other",
            last_name="Student",
        )
        category = CourseCategory.objects.create(name="Auth Test", slug="auth-test")
        self.course = Course.objects.create(
            category=category,
            title="Authorization Test Course",
            slug="authorization-test-course",
            short_description="Synthetic authorization fixture.",
            description="Synthetic authorization fixture only.",
            curriculum="Synthetic",
            academic_level="Acceptance",
            price="100.00",
            status=Course.Status.PUBLISHED,
        )

    @staticmethod
    def payload(student: StudentRecord, *, confirmed: bool = True) -> dict:
        return {
            "id": str(student.supabase_user_id),
            "email": student.email,
            "email_confirmed_at": "2026-10-09T12:00:00Z" if confirmed else None,
            "user_metadata": {
                "first_name": student.first_name,
                "last_name": student.last_name,
            },
        }

    def get_as(self, student: StudentRecord, url: str, *, confirmed: bool = True):
        with patch.object(
            SupabaseStudentAuthentication,
            "_validate_token",
            return_value=self.payload(student, confirmed=confirmed),
        ):
            return self.client.get(
                url,
                secure=True,
                HTTP_AUTHORIZATION="Bearer synthetic-unit-token",
            )

    def test_anonymous_student_api_is_rejected(self):
        response = self.client.get(reverse("student-courses"), secure=True)
        self.assertEqual(response.status_code, 401)

    def test_malformed_authorization_header_is_rejected(self):
        response = self.client.get(
            reverse("student-courses"),
            secure=True,
            HTTP_AUTHORIZATION="Token not-a-bearer-token",
        )
        self.assertEqual(response.status_code, 401)

    def test_unverified_supabase_user_is_rejected(self):
        response = self.get_as(
            self.student,
            reverse("student-courses"),
            confirmed=False,
        )
        self.assertEqual(response.status_code, 401)

    def test_confirmed_active_supabase_user_can_enter_student_api(self):
        response = self.get_as(self.student, reverse("student-courses"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_inactive_student_profile_is_rejected(self):
        self.student.is_active = False
        self.student.save(update_fields=["is_active", "updated_at"])

        response = self.get_as(self.student, reverse("student-courses"))
        self.assertEqual(response.status_code, 401)

    def test_payment_status_is_owner_scoped(self):
        payment = Payment.objects.create(
            reference="AUTH-OWNER-TEST-001",
            student=self.other_student,
            course=self.course,
            provider=Payment.Provider.PAYFAST,
            amount=self.course.price,
            status=Payment.Status.PENDING,
        )
        url = reverse("student-payment-status", args=[payment.reference])

        cross_user = self.get_as(self.student, url)
        self.assertEqual(cross_user.status_code, 404)

        owner = self.get_as(self.other_student, url)
        self.assertEqual(owner.status_code, 200)
        self.assertEqual(owner.data["payment_reference"], payment.reference)

    @override_settings(ACCEPTANCE_GITHUB_OIDC_ENABLED=False)
    def test_acceptance_header_cannot_enable_synthetic_identity_in_production(self):
        response = self.client.get(
            reverse("student-courses"),
            secure=True,
            HTTP_AUTHORIZATION="Bearer synthetic-test-token",
            HTTP_X_AMARIS_ACCEPTANCE="github-actions",
        )
        self.assertEqual(response.status_code, 401)
