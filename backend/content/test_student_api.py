from __future__ import annotations

import os
import uuid
from decimal import Decimal
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from content.authentication import SupabasePrincipal
from content.models import Course, CourseCategory, CourseModule, Enrollment, Lesson, Payment, StudentRecord
from content.payment_models import NotificationOutbox
from content.services.payfast_security import (
    PayFastConfig,
    PayFastVerifier,
    build_payfast_checkout_fields,
    generate_payfast_signature,
)
from content.student_views import (
    CheckoutStartView,
    EnrollmentProgressView,
    PaymentStatusView,
    ProtectedLessonView,
    StudentDashboardView,
)
from content.tasks import deliver_notification_outbox


class StudentApiFixture(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.principal = SupabasePrincipal(
            id="00000000-0000-4000-8000-000000000201",
            email="student.api@example.test",
            email_verified=True,
            metadata={"first_name": "Synthetic", "last_name": "Student"},
        )
        self.other_principal = SupabasePrincipal(
            id="00000000-0000-4000-8000-000000000202",
            email="other.api@example.test",
            email_verified=True,
            metadata={"first_name": "Other", "last_name": "Student"},
        )
        self.category = CourseCategory.objects.create(name="Student API", slug="student-api")
        self.course = Course.objects.create(
            category=self.category,
            title="Synthetic Student API Course",
            slug="synthetic-student-api-course",
            short_description="Synthetic fixture",
            description="No real student data.",
            curriculum="Synthetic",
            academic_level="Test",
            price=Decimal("950.00"),
            status=Course.Status.PUBLISHED,
        )
        self.module = CourseModule.objects.create(
            course=self.course,
            title="Module One",
            order=1,
            is_published=True,
        )
        self.lesson = Lesson.objects.create(
            module=self.module,
            title="Synthetic Lesson",
            slug="synthetic-lesson",
            lesson_body="Synthetic lesson body.",
            duration_minutes=10,
            order=1,
            is_published=True,
        )

    def request(self, method, path, *, principal=None, data=None):
        builder = getattr(self.factory, method.lower())
        request = builder(path, data=data or {}, format="json")
        force_authenticate(request, user=principal or self.principal)
        return request

    @staticmethod
    def student(principal: SupabasePrincipal):
        return StudentRecord.objects.get(supabase_user_id=principal.id)


class StudentCheckoutApiTests(StudentApiFixture):
    payfast_env = {
        "PAYFAST_MODE": "sandbox",
        "PAYFAST_MERCHANT_ID": "10000100",
        "PAYFAST_MERCHANT_KEY": "synthetic-key",
        "PAYFAST_PASSPHRASE": "synthetic-passphrase",
        "PAYFAST_RETURN_URL": "https://example.test/payments/status/{reference}",
        "PAYFAST_CANCEL_URL": "https://example.test/payments/cancelled?reference={reference}",
        "PAYFAST_NOTIFY_URL": "https://cms.example.test/api/v1/payments/payfast/itn/",
    }

    def test_checkout_is_server_priced_owner_bound_and_private(self):
        with patch.dict(os.environ, self.payfast_env, clear=False):
            request = self.request(
                "post",
                "/api/v1/student/checkout/",
                data={
                    "course_slug": self.course.slug,
                    "idempotency_key": "test0001",
                    "amount": "1.00",
                    "student_id": str(self.other_principal.id),
                },
            )
            response = CheckoutStartView.as_view()(request)

        self.assertEqual(response.status_code, 201)
        payment = Payment.objects.get(reference=response.data["reference"])
        self.assertEqual(payment.amount, self.course.price)
        self.assertEqual(str(payment.student.supabase_user_id), self.principal.id)
        self.assertEqual(response.data["fields"]["amount"], "950.00")
        self.assertEqual(response["Cache-Control"], "private, no-store, max-age=0")
        self.assertIn("Authorization", response["Vary"])

    def test_other_student_cannot_read_payment_status(self):
        student = StudentRecord.objects.create(
            supabase_user_id=uuid.UUID(self.principal.id),
            email=self.principal.email,
            first_name="Synthetic",
            last_name="Student",
        )
        payment = Payment.objects.create(
            reference="PF-owner-only-001",
            student=student,
            course=self.course,
            provider=Payment.Provider.PAYFAST,
            amount=self.course.price,
            status=Payment.Status.PENDING,
        )
        request = self.request(
            "get",
            f"/api/v1/student/payments/{payment.reference}/",
            principal=self.other_principal,
        )
        response = PaymentStatusView.as_view()(request, reference=payment.reference)
        self.assertEqual(response.status_code, 404)

    def test_unverified_student_cannot_start_checkout(self):
        unverified = SupabasePrincipal(
            id="00000000-0000-4000-8000-000000000203",
            email="unverified.api@example.test",
            email_verified=False,
            metadata={},
        )
        with patch.dict(os.environ, self.payfast_env, clear=False):
            request = self.request(
                "post",
                "/api/v1/student/checkout/",
                principal=unverified,
                data={"course_slug": self.course.slug, "idempotency_key": "test0002"},
            )
            response = CheckoutStartView.as_view()(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Payment.objects.count(), 0)


class StudentResumeApiTests(StudentApiFixture):
    def setUp(self):
        super().setUp()
        self.student_record = StudentRecord.objects.create(
            supabase_user_id=uuid.UUID(self.principal.id),
            email=self.principal.email,
            first_name="Synthetic",
            last_name="Student",
        )
        self.enrollment = Enrollment.objects.create(
            student=self.student_record,
            course=self.course,
            status=Enrollment.Status.ACTIVE,
        )

    def test_progress_round_trip_and_dashboard_continue_lesson(self):
        request = self.request(
            "put",
            f"/api/v1/student/courses/{self.course.slug}/progress/",
            data={
                "lesson_slug": self.lesson.slug,
                "position_seconds": 125,
                "completed": False,
            },
        )
        response = EnrollmentProgressView.as_view()(request, course_slug=self.course.slug)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["last_position_seconds"], 125)
        self.assertEqual(response.data["last_lesson"]["slug"], self.lesson.slug)

        dashboard_request = self.request("get", "/api/v1/student/dashboard/")
        dashboard = StudentDashboardView.as_view()(dashboard_request)
        self.assertEqual(dashboard.status_code, 200)
        item = dashboard.data["enrollments"][0]
        self.assertEqual(item["continue_lesson"]["slug"], self.lesson.slug)
        self.assertEqual(item["last_position_seconds"], 125)

        lesson_request = self.request(
            "get",
            f"/api/v1/student/courses/{self.course.slug}/lessons/{self.lesson.slug}/",
        )
        lesson_response = ProtectedLessonView.as_view()(
            lesson_request,
            course_slug=self.course.slug,
            lesson_slug=self.lesson.slug,
        )
        self.assertEqual(lesson_response.status_code, 200)
        self.assertEqual(lesson_response.data["position_seconds"], 125)
        self.assertEqual(lesson_response["Cache-Control"], "private, no-store, max-age=0")

    def test_other_student_cannot_read_enrolled_lesson_or_progress(self):
        progress_request = self.request(
            "get",
            f"/api/v1/student/courses/{self.course.slug}/progress/",
            principal=self.other_principal,
        )
        progress = EnrollmentProgressView.as_view()(progress_request, course_slug=self.course.slug)
        self.assertEqual(progress.status_code, 404)

        lesson_request = self.request(
            "get",
            f"/api/v1/student/courses/{self.course.slug}/lessons/{self.lesson.slug}/",
            principal=self.other_principal,
        )
        lesson = ProtectedLessonView.as_view()(
            lesson_request,
            course_slug=self.course.slug,
            lesson_slug=self.lesson.slug,
        )
        self.assertEqual(lesson.status_code, 404)


class PayFastLiveConfigurationTests(TestCase):
    def test_hosted_checkout_signature_is_generated_from_backend_fields(self):
        config = PayFastConfig(
            mode="live",
            merchant_id="merchant",
            merchant_key="key",
            passphrase="passphrase",
            return_url="https://app.example.test/payments/status/{reference}",
            cancel_url="https://app.example.test/payments/cancelled?reference={reference}",
            notify_url="https://cms.example.test/api/v1/payments/payfast/itn/",
        )
        fields = build_payfast_checkout_fields(
            {
                "m_payment_id": "PF-reference-001",
                "amount": "950.00",
                "item_name": "Synthetic Course",
                "custom_str1": "00000000-0000-4000-8000-000000000201",
                "custom_str2": "synthetic-course",
            },
            config=config,
        )
        signature = fields.pop("signature")
        self.assertEqual(signature, generate_payfast_signature(fields, passphrase=config.passphrase))
        self.assertEqual(config.process_url, "https://www.payfast.co.za/eng/process")
        self.assertIn("PF-reference-001", fields["return_url"])

    def test_verifier_rejects_wrong_source_before_server_validation(self):
        config = PayFastConfig(
            mode="sandbox",
            merchant_id="10000100",
            merchant_key="key",
            passphrase="passphrase",
            return_url="https://app.example.test/return",
            cancel_url="https://app.example.test/cancel",
            notify_url="https://cms.example.test/notify",
        )
        payload = {
            "merchant_id": "10000100",
            "m_payment_id": "PF-001",
            "amount_gross": "950.00",
        }
        payload["signature"] = generate_payfast_signature(payload, passphrase=config.passphrase)
        checker = patch("builtins.print")
        with checker:
            verifier = PayFastVerifier(
                config=config,
                source_ip="198.51.100.10",
                allowed_sources=("203.0.113.0/24",),
                valid_data_checker=lambda _payload: True,
            )
            self.assertFalse(verifier.verify_notification(payload))


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="Amaris Mathematics Academy <no-reply@example.test>",
)
class TransactionalEmailOutboxTests(StudentApiFixture):
    def test_payment_notification_is_delivered_once_and_marks_sent(self):
        payment = Payment.objects.create(
            reference="PF-email-001",
            student=StudentRecord.objects.create(
                supabase_user_id=uuid.UUID(self.principal.id),
                email=self.principal.email,
                first_name="Synthetic",
                last_name="Student",
            ),
            course=self.course,
            provider=Payment.Provider.PAYFAST,
            amount=self.course.price,
            status=Payment.Status.PAID,
        )
        outbox = NotificationOutbox.objects.create(
            payment=payment,
            destination=self.principal.email,
            payload={
                "course": self.course.title,
                "payment_reference": payment.reference,
                "invoice_number": "INV-PF-email-001",
                "ticket_number": "TKT-PF-email-001",
            },
        )

        self.assertTrue(deliver_notification_outbox.run(outbox.id))
        outbox.refresh_from_db()
        self.assertEqual(outbox.status, NotificationOutbox.Status.SENT)
        self.assertEqual(outbox.attempts, 1)
        self.assertEqual(len(mail.outbox), 1)

        self.assertTrue(deliver_notification_outbox.run(outbox.id))
        self.assertEqual(len(mail.outbox), 1)
