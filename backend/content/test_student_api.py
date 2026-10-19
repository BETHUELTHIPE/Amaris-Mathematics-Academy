from __future__ import annotations

import os
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory, APITestCase

from content.authentication import SupabaseStudentAuthentication, SupabaseStudentPrincipal
from content.models import (
    Course,
    CourseCategory,
    CourseModule,
    Enrollment,
    Lesson,
    LiveClassBooking,
    Payment,
    StudentRecord,
    TutorAvailabilitySlot,
    VideoRequest,
)
from content.payment_models import Invoice, NotificationOutbox, ServiceTicket


class AcceptanceIdentityTests(APITestCase):
    @override_settings(ACCEPTANCE_GITHUB_OIDC_ENABLED=True)
    def test_distinct_virtual_students_can_seed_checkout_and_poll_only_their_payment(self):
        claims = {
            "repository": "BETHUELTHIPE/Amaris-Mathematics-Academy",
            "event_name": "push",
            "environment": "staging",
            "ref": "refs/heads/main",
            "run_id": "36052676350",
        }
        identities = [
            "00000000-0000-4000-8000-000000000001",
            "00000000-0000-4000-8000-000000000002",
        ]
        references = []
        with (
            patch(
                "content.authentication._GITHUB_JWK_CLIENT.get_signing_key_from_jwt",
                return_value=SimpleNamespace(key="mock-key"),
            ),
            patch("content.authentication.decode_jwt", return_value=claims),
        ):
            for identity in identities:
                headers = {
                    "HTTP_AUTHORIZATION": "Bearer synthetic-test-token",
                    "HTTP_X_AMARIS_ACCEPTANCE": "github-actions",
                    "HTTP_X_AMARIS_ACCEPTANCE_STUDENT": identity,
                }
                seed = self.client.post(reverse("student-acceptance-seed"), {}, format="json", secure=True, **headers)
                self.assertEqual(seed.status_code, 200)
                checkout = self.client.post(
                    reverse("student-checkout"),
                    {
                        "course_slug": seed.data["course_slug"],
                        "idempotency_key": f"capacity-{identity.replace('-', '')}",
                    },
                    format="json",
                    secure=True,
                    **headers,
                )
                self.assertEqual(checkout.status_code, 201)
                reference = checkout.data["payment_reference"]
                references.append(reference)
                own = self.client.get(reverse("student-payment-status", args=[reference]), secure=True, **headers)
                self.assertEqual(own.status_code, 200)
                self.assertEqual(own.data["status"], "pending")
            other_student_headers = {
                "HTTP_AUTHORIZATION": "Bearer synthetic-test-token",
                "HTTP_X_AMARIS_ACCEPTANCE": "github-actions",
                "HTTP_X_AMARIS_ACCEPTANCE_STUDENT": identities[0],
            }
            cross_user = self.client.get(
                reverse("student-payment-status", args=[references[1]]),
                secure=True,
                **other_student_headers,
            )
            self.assertEqual(cross_user.status_code, 404)

    @override_settings(ACCEPTANCE_GITHUB_OIDC_ENABLED=True)
    def test_signed_run_has_isolated_synthetic_students_without_repeated_writes(self):
        claims = {
            "repository": "BETHUELTHIPE/Amaris-Mathematics-Academy",
            "event_name": "push",
            "environment": "staging",
            "ref": "refs/heads/main",
            "run_id": "36052676350",
        }
        factory = APIRequestFactory()
        authenticator = SupabaseStudentAuthentication()

        def principal(identifier):
            request = factory.get(
                "/api/v1/student/courses/",
                HTTP_AUTHORIZATION="Bearer synthetic-test-token",
                HTTP_X_AMARIS_ACCEPTANCE="github-actions",
                HTTP_X_AMARIS_ACCEPTANCE_STUDENT=identifier,
            )
            return authenticator.authenticate(request)[0]

        with (
            patch(
                "content.authentication._GITHUB_JWK_CLIENT.get_signing_key_from_jwt",
                return_value=SimpleNamespace(key="mock-key"),
            ),
            patch("content.authentication.decode_jwt", return_value=claims),
        ):
            first = principal("00000000-0000-4000-8000-000000000001")
            first_updated_at = first.student.updated_at
            same = principal("00000000-0000-4000-8000-000000000001")
            other = principal("00000000-0000-4000-8000-000000000002")
            first.student.refresh_from_db()

            self.assertEqual(first.pk, same.pk)
            self.assertEqual(first.student.updated_at, first_updated_at)
            self.assertNotEqual(first.pk, other.pk)
            self.assertNotEqual(first.email, other.email)
            self.assertEqual(StudentRecord.objects.count(), 2)

            with self.assertRaises(AuthenticationFailed):
                principal("invalid-student")

    @override_settings(ACCEPTANCE_GITHUB_OIDC_ENABLED=False)
    def test_synthetic_identity_cannot_be_enabled_by_headers_alone(self):
        request = APIRequestFactory().get(
            "/api/v1/student/courses/",
            HTTP_AUTHORIZATION="Bearer synthetic-test-token",
            HTTP_X_AMARIS_ACCEPTANCE="github-actions",
            HTTP_X_AMARIS_ACCEPTANCE_STUDENT="00000000-0000-4000-8000-000000000001",
        )
        with self.assertRaises(AuthenticationFailed):
            SupabaseStudentAuthentication().authenticate(request)


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
        courses = self.client.get(reverse("student-courses"), secure=True)
        self.assertEqual(courses.data[0]["course"]["first_lesson_slug"], self.lesson.slug)
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

    def test_course_start_skips_hidden_and_future_lessons(self):
        self.authenticate()
        for published, publish_at in ((False, None), (True, timezone.now() + timedelta(days=1))):
            self.lesson.is_published = published
            self.lesson.publish_at = publish_at
            self.lesson.save()
            response = self.client.get(reverse("student-courses"), secure=True)
            self.assertEqual(response.data[0]["course"]["first_lesson_slug"], "")
        self.lesson.is_published = True
        self.lesson.publish_at = None
        self.lesson.save()
        self.lesson.module.is_published = False
        self.lesson.module.save()
        self.assertEqual(
            self.client.get(reverse("student-courses"), secure=True).data[0]["course"]["first_lesson_slug"], ""
        )

    def test_orders_and_notifications_are_private_and_include_paid_course_receipts(self):
        paid_at = timezone.now()
        payment = Payment.objects.create(
            reference="PAY-STUDENT-ORDER-001",
            student=self.student,
            course=self.course,
            enrollment=self.enrollment,
            provider=Payment.Provider.PAYFAST,
            provider_reference="provider-student-order-001",
            amount=Decimal("950.00"),
            currency="ZAR",
            status=Payment.Status.PAID,
            paid_at=paid_at,
            gateway_verified_at=paid_at,
        )
        invoice = Invoice.objects.create(
            payment=payment,
            invoice_number="INV-STUDENT-ORDER-001",
            student=self.student,
            course=self.course,
            amount=payment.amount,
            currency=payment.currency,
            issued_at=paid_at,
        )
        NotificationOutbox.objects.create(
            payment=payment,
            destination=self.student.email,
            status=NotificationOutbox.Status.SENT,
        )
        Payment.objects.create(
            reference="PAY-OTHER-ORDER-001",
            student=self.other,
            course=self.course,
            provider=Payment.Provider.PAYFAST,
            amount=Decimal("950.00"),
            currency="ZAR",
            status=Payment.Status.PENDING,
        )

        self.authenticate()
        orders = self.client.get(reverse("student-orders"), secure=True)
        self.assertEqual(orders.status_code, 200)
        self.assertEqual(orders["Cache-Control"], "private, no-store")
        self.assertEqual([item["reference"] for item in orders.data], [payment.reference])
        self.assertEqual(orders.data[0]["invoice_number"], invoice.invoice_number)
        self.assertTrue(orders.data[0]["invoice_ready"])

        notifications = self.client.get(reverse("student-notifications"), secure=True)
        self.assertEqual(notifications.status_code, 200)
        self.assertEqual(notifications["Cache-Control"], "private, no-store")
        self.assertEqual(len(notifications.data), 1)
        self.assertEqual(notifications.data[0]["category"], "payment")
        self.assertNotIn("other", str(notifications.data).lower())

        with (
            TemporaryDirectory() as directory,
            override_settings(
                STORAGES={
                    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                    "student_private": {
                        "BACKEND": "django.core.files.storage.FileSystemStorage",
                        "OPTIONS": {"location": str(Path(directory) / "student"), "allow_overwrite": True},
                    },
                    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
                }
            ),
        ):
            invoice_url = reverse("student-course-invoice", args=[payment.reference])
            response = self.client.get(invoice_url, secure=True)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Cache-Control"], "private, no-store")
            self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF"))

            self.authenticate(self.other)
            self.assertEqual(self.client.get(invoice_url, secure=True).status_code, 404)

        self.authenticate()
        for operation in ("exists", "open"):
            storage = Mock()
            storage.exists.return_value = True
            getattr(storage, operation).side_effect = ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "private storage error"}}, operation
            )
            with patch("content.student_views.storages", {"student_private": storage}):
                unavailable = self.client.get(invoice_url, secure=True)
            self.assertEqual(unavailable.status_code, 503)
            self.assertEqual(unavailable["Cache-Control"], "private, no-store")
            self.assertNotIn("private storage error", str(unavailable.data))

        payment.gateway_verified_at = None
        payment.save(update_fields=["gateway_verified_at"])
        self.assertEqual(self.client.get(invoice_url, secure=True).status_code, 404)

    def test_booking_and_video_history_never_exposes_another_student_or_private_payloads(self):
        tutor = get_user_model().objects.create_user(username="dashboard.synthetic.tutor")
        start = timezone.now() + timedelta(days=1)
        slot = TutorAvailabilitySlot.objects.create(
            tutor=tutor,
            programme="caps",
            subject="mathematics",
            level="Grade 12",
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            zoom_join_url="https://zoom.example.test/private",
        )
        for index, student in enumerate((self.student, self.other)):
            LiveClassBooking.objects.create(
                reference=f"LC-DASHBOARD-{index}",
                idempotency_key=f"dashboard-booking-{index}",
                student=student,
                slot=slot,
                programme="caps",
                subject="mathematics",
                level="Grade 12",
                topic="Synthetic calculus",
                status=LiveClassBooking.Status.COMPLETED,
                confirmation_sent_at=start,
                reminder_sent_at=start,
            )
            VideoRequest.objects.create(
                reference=f"VR-DASHBOARD-{index}",
                idempotency_key=f"dashboard-video-{index}",
                student=student,
                programme="caps",
                subject="mathematics",
                level="Grade 12",
                topic="Synthetic algebra",
                request_type="chapter_topic",
                amount="450.00",
                confirmation_sent_at=start,
                instructions="Private student instructions",
                video_external_id="private/object.mp4",
            )
        paid_booking = LiveClassBooking.objects.get(reference="LC-DASHBOARD-0")
        paid_booking.status = LiveClassBooking.Status.CONFIRMED
        paid_booking.invoice_number = "INV-SYNTH-DASHBOARD-0"
        paid_booking.gateway_verified_at = timezone.now()
        paid_booking.paid_at = timezone.now()
        paid_booking.confirmation_sent_at = None
        paid_booking.save(update_fields=[
            "status", "invoice_number", "gateway_verified_at", "paid_at", "confirmation_sent_at",
        ])
        self.authenticate()
        orders = self.client.get(reverse("student-orders"), secure=True)
        self.assertEqual({item["reference"] for item in orders.data}, {"LC-DASHBOARD-0", "VR-DASHBOARD-0"})
        order = next(item for item in orders.data if item["reference"] == "LC-DASHBOARD-0")
        self.assertTrue(order["invoice_ready"], "Verified paid invoice must not depend on SMTP success")
        paid_booking.gateway_verified_at = None
        paid_booking.save(update_fields=["gateway_verified_at"])
        unpaid = self.client.get(reverse("student-orders"), secure=True)
        self.assertFalse(next(item for item in unpaid.data if item["reference"] == "LC-DASHBOARD-0")["invoice_ready"])
        self.assertNotIn("private", str(orders.data).lower())
        notifications = self.client.get(reverse("student-notifications"), secure=True)
        self.assertEqual(len(notifications.data), 3)
        self.assertNotIn("DASHBOARD-1", str(notifications.data))
        self.assertNotIn("private", str(notifications.data).lower())
        self.assertEqual(self.client.post(reverse("student-orders"), {}, secure=True).status_code, 405)
        self.assertEqual(self.client.post(reverse("student-notifications"), {}, secure=True).status_code, 405)
        self.authenticate(self.other)
        others = self.client.get(reverse("student-orders"), secure=True)
        self.assertEqual({item["reference"] for item in others.data}, {"LC-DASHBOARD-1", "VR-DASHBOARD-1"})

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

        for mode, alias in (("live", ""), ("", "live"), ("sandbox", "live"), ("", "invalid")):
            with (
                self.subTest(mode=mode, alias=alias),
                patch.dict(os.environ, {"PAYFAST_MODE": mode, "PAYFAST_ENV": alias}),
            ):
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
        self.assertEqual(self.client.get(reverse("student-orders"), secure=True).status_code, 401)
        self.assertEqual(self.client.get(reverse("student-notifications"), secure=True).status_code, 401)
