from __future__ import annotations

import os
import uuid
from decimal import Decimal
from unittest.mock import patch

from django.urls import reverse
from rest_framework.test import APITestCase

from content.authentication import SupabaseStudentPrincipal
from content.models import Course, CourseCategory, CourseModule, Enrollment, Lesson, Payment, StudentRecord
from content.payment_models import Invoice, NotificationOutbox, ServiceTicket


class StudentJourneyApiTests(APITestCase):
    def setUp(self):
        self.student = StudentRecord.objects.create(
            supabase_user_id=uuid.UUID("00000000-0000-4000-8000-000000000201"),
            email="journey.student@example.test",
            first_name="Journey",
            last_name="Student",
        )
        self.other = StudentRecord.objects.create(
            supabase_user_id=uuid.UUID("00000000-0000-4000-8000-000000000202"),
            email="other.journey@example.test",
            first_name="Other",
            last_name="Student",
        )
        category = CourseCategory.objects.create(name="Journey", slug="journey")
        self.course = Course.objects.create(
            category=category,
            title="Journey Mathematics",
            slug="journey-mathematics",
            short_description="Synthetic journey course",
            description="Synthetic journey course used only in automated tests.",
            curriculum="Synthetic",
            academic_level="Test",
            price=Decimal("950.00"),
            status=Course.Status.PUBLISHED,
        )
        module = CourseModule.objects.create(course=self.course, title="Module 1", order=1, is_published=True)
        self.lesson = Lesson.objects.create(
            module=module,
            title="Algebra foundations",
            slug="algebra-foundations",
            order=1,
            is_published=True,
        )
        self.enrollment = Enrollment.objects.create(
            student=self.student,
            course=self.course,
            status=Enrollment.Status.ACTIVE,
        )

    def authenticate(self, student=None):
        student = student or self.student
        self.client.force_authenticate(
            user=SupabaseStudentPrincipal(
                student=student,
                supabase_user_id=str(student.supabase_user_id),
                email=student.email,
            )
        )

    def test_checkout_creation_and_status_polling_use_server_owned_facts(self):
        self.authenticate()
        checkout = self.client.post(
            reverse("student-checkout"),
            {"course_slug": self.course.slug, "idempotency_key": "journey-checkout-001"},
            format="json",
            secure=True,
        )
        self.assertEqual(checkout.status_code, 201)
        self.assertEqual(checkout.data["status"], Payment.Status.PENDING)
        self.assertEqual(checkout.data["fields"]["amount"], "950.00")
        self.assertIn("sandbox.payfast.co.za", checkout.data["gateway_url"])

        reference = checkout.data["payment_reference"]
        status_response = self.client.get(reverse("student-payment-status", args=[reference]), secure=True)
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.data["status"], Payment.Status.PENDING)

        self.authenticate(self.other)
        cross_user = self.client.get(reverse("student-payment-status", args=[reference]), secure=True)
        self.assertEqual(cross_user.status_code, 404)

    def test_last_lesson_resume_persists_and_is_student_scoped(self):
        self.authenticate()
        update = self.client.patch(
            reverse("student-progress"),
            {
                "course_slug": self.course.slug,
                "lesson_slug": self.lesson.slug,
                "position_seconds": 347,
                "progress_percent": 42,
            },
            format="json",
            secure=True,
        )
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.data["last_lesson"]["slug"], self.lesson.slug)
        self.assertEqual(update.data["last_position_seconds"], 347)
        self.assertEqual(update.data["progress_percent"], 42)

        resumed = self.client.get(reverse("student-resume", args=[self.course.slug]), secure=True)
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(resumed.data["last_lesson"]["slug"], self.lesson.slug)
        self.assertEqual(resumed.data["last_position_seconds"], 347)

        self.authenticate(self.other)
        cross_user = self.client.get(reverse("student-resume", args=[self.course.slug]), secure=True)
        self.assertEqual(cross_user.status_code, 404)

    def test_acceptance_payment_completion_uses_real_fulfillment_path_in_sandbox(self):
        self.course.slug = "acceptance-capacity-mathematics"
        self.course.save(update_fields=["slug", "updated_at"])
        principal = SupabaseStudentPrincipal(
            student=self.student,
            supabase_user_id=str(self.student.supabase_user_id),
            email=self.student.email,
        )
        self.client.force_authenticate(
            user=principal,
            token={"provider": "github-actions-oidc"},
        )

        with patch.dict(os.environ, {"PAYFAST_MODE": "sandbox"}):
            checkout = self.client.post(
                reverse("student-checkout"),
                {
                    "course_slug": self.course.slug,
                    "idempotency_key": "acceptance-paid-001",
                },
                format="json",
                secure=True,
            )
            self.assertEqual(checkout.status_code, 201)
            reference = checkout.data["payment_reference"]
            completed = self.client.post(
                reverse("student-acceptance-payment-complete", args=[reference]),
                {},
                format="json",
                secure=True,
            )

        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.data["status"], Payment.Status.PAID)
        self.assertEqual(completed.data["enrollment_status"], Enrollment.Status.ACTIVE)
        payment = Payment.objects.get(reference=reference)
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertIsNotNone(payment.gateway_verified_at)
        self.assertTrue(Invoice.objects.filter(payment=payment).exists())
        self.assertTrue(ServiceTicket.objects.filter(payment=payment).exists())
        self.assertTrue(NotificationOutbox.objects.filter(payment=payment).exists())

    def test_acceptance_payment_completion_is_disabled_in_live_payfast_mode(self):
        self.course.slug = "acceptance-capacity-mathematics"
        self.course.save(update_fields=["slug", "updated_at"])
        principal = SupabaseStudentPrincipal(
            student=self.student,
            supabase_user_id=str(self.student.supabase_user_id),
            email=self.student.email,
        )
        self.client.force_authenticate(
            user=principal,
            token={"provider": "github-actions-oidc"},
        )

        with patch.dict(os.environ, {"PAYFAST_MODE": "sandbox"}):
            checkout = self.client.post(
                reverse("student-checkout"),
                {
                    "course_slug": self.course.slug,
                    "idempotency_key": "acceptance-live-001",
                },
                format="json",
                secure=True,
            )
        reference = checkout.data["payment_reference"]

        with patch.dict(os.environ, {"PAYFAST_MODE": "live"}):
            completed = self.client.post(
                reverse("student-acceptance-payment-complete", args=[reference]),
                {},
                format="json",
                secure=True,
            )

        self.assertEqual(completed.status_code, 403)
        self.assertEqual(Payment.objects.get(reference=reference).status, Payment.Status.PENDING)

    def test_anonymous_student_journey_is_rejected(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            reverse("student-checkout"),
            {"course_slug": self.course.slug, "idempotency_key": "anonymous-checkout"},
            format="json",
            secure=True,
        )
        self.assertEqual(response.status_code, 401)
