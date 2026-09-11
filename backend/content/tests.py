import uuid
from unittest.mock import patch

from django.apps import apps
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    Course,
    CourseCategory,
    CourseModule,
    Enrollment,
    Lesson,
    Payment,
    SiteSettings,
    StudentRecord,
    VideoAsset,
)
from .services.reconciliation import reconcile_verified_payments


class AdminRegistrationTests(TestCase):
    def test_every_content_model_is_registered(self):
        unregistered = [
            model.__name__ for model in apps.get_app_config("content").get_models() if model not in admin.site._registry
        ]
        self.assertEqual(unregistered, [])

    def test_jazzmin_admin_index_loads(self):
        user = get_user_model().objects.create_superuser(
            username="admin-test",
            email="admin-test@example.com",
            password="Strong-Test-Password-123!",
        )
        self.client.force_login(user)
        response = self.client.get(reverse("admin:index"), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Amaris Academy")


class PublicContentApiTests(TestCase):
    def setUp(self):
        self.category = CourseCategory.objects.create(name="CAPS", slug="caps")

    def test_only_published_courses_are_public(self):
        Course.objects.create(
            category=self.category,
            title="Draft course",
            slug="draft-course",
            short_description="Not ready",
            description="Draft",
            curriculum="CAPS",
            academic_level="Grade 12",
            price=950,
            status=Course.Status.DRAFT,
        )
        Course.objects.create(
            category=self.category,
            title="Published course",
            slug="published-course",
            short_description="Ready",
            description="Published",
            curriculum="CAPS",
            academic_level="Grade 12",
            price=950,
            status=Course.Status.PUBLISHED,
        )
        response = self.client.get(reverse("courses-list"), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["results"][0]["slug"], "published-course")

    def test_site_settings_endpoint(self):
        SiteSettings.objects.create()
        response = self.client.get(reverse("site-settings"), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["site_name"], "Amaris Mathematics Academy")

    @override_settings(
        CACHES={
            "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "throttles"},
            "public_content": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "public-content",
            },
        }
    )
    def test_course_list_is_lightweight_and_cached(self):
        course = Course.objects.create(
            category=self.category,
            title="Cached course",
            slug="cached-course",
            short_description="Ready",
            description="Long detail-page copy",
            curriculum="CAPS",
            academic_level="Grade 12",
            price=950,
            status=Course.Status.PUBLISHED,
        )
        CourseModule.objects.create(course=course, title="Algebra", order=1, is_published=True)
        caches["public_content"].clear()

        first = self.client.get(reverse("courses-list"), secure=True)
        payload = first.json()["results"][0]
        self.assertNotIn("modules", payload)
        self.assertNotIn("outcomes", payload)
        self.assertNotIn("description", payload)

        with self.assertNumQueries(0):
            second = self.client.get(reverse("courses-list"), secure=True)
        self.assertEqual(second.content, first.content)


class PermissionTests(TestCase):
    def test_anonymous_and_non_staff_users_cannot_enter_admin(self):
        anonymous = self.client.get(reverse("admin:index"), secure=True)
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn("/admin/login/", anonymous.headers["Location"])

        user = get_user_model().objects.create_user(
            username="student-test",
            email="student-test@example.com",
            password="Strong-Test-Password-123!",
        )
        self.client.force_login(user)
        non_staff = self.client.get(reverse("admin:index"), secure=True)
        self.assertEqual(non_staff.status_code, 302)
        self.assertIn("/admin/login/", non_staff.headers["Location"])

    def test_public_course_api_never_exposes_private_video_identifiers(self):
        category = CourseCategory.objects.create(name="Matric", slug="matric")
        course = Course.objects.create(
            category=category,
            title="Matric Algebra",
            slug="matric-algebra",
            short_description="CAPS algebra revision",
            description="Structured algebra revision.",
            curriculum="CAPS",
            academic_level="Grade 12",
            price=950,
            status=Course.Status.PUBLISHED,
        )
        module = CourseModule.objects.create(course=course, title="Algebra", order=1, is_published=True)
        video = VideoAsset.objects.create(
            title="Private algebra lesson",
            provider=VideoAsset.Provider.YOUTUBE,
            youtube_video_id="private-video-id",
            is_published=False,
        )
        Lesson.objects.create(
            module=module,
            title="Lesson 1",
            slug="lesson-1",
            order=1,
            video=video,
            is_published=True,
        )

        response = self.client.get(reverse("courses-detail", kwargs={"slug": course.slug}), secure=True)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertNotIn("private-video-id", body)


class HealthAndMetricsTests(TestCase):
    def test_liveness_and_readiness_do_not_disclose_infrastructure(self):
        live = self.client.get(reverse("health-live"), secure=True)
        ready = self.client.get(reverse("health-ready"), secure=True)

        self.assertEqual(live.status_code, 200)
        self.assertEqual(live.json(), {"status": "ok"})
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.json(), {"status": "ready"})
        self.assertNotContains(live, "postgres", status_code=200)
        self.assertNotContains(ready, "redis", status_code=200)

    @patch("amaris_cms.urls.Redis.from_url", side_effect=ConnectionError)
    def test_redis_failure_degrades_dependencies_but_not_readiness(self, _redis):
        ready = self.client.get(reverse("health-ready"), secure=True)
        dependencies = self.client.get(reverse("health-dependencies"), secure=True)

        self.assertEqual(ready.status_code, 200)
        self.assertEqual(dependencies.status_code, 200)
        self.assertEqual(dependencies.json()["status"], "degraded")
        self.assertTrue(dependencies.json()["dependencies"]["postgresql"])
        self.assertFalse(dependencies.json()["dependencies"]["redis"])

    def test_prometheus_metrics_endpoint_is_available_to_private_scraper(self):
        response = self.client.get("/metrics", secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response.headers["Content-Type"])


class ErrorRecoveryTests(TestCase):
    def test_branded_error_pages_are_safe_and_traceable(self):
        for status in (400, 403, 404, 429, 500):
            with self.subTest(status=status):
                response = self.client.get(reverse(f"error-{status}"), secure=True)
                self.assertEqual(response.status_code, status)
                self.assertContains(response, "Amaris Mathematics Academy", status_code=status)
                self.assertContains(response, "Support reference", status_code=status)
                self.assertRegex(response.headers["X-Correlation-ID"], r"^AMR-[A-Z0-9-]+$")
                body = response.content.decode().lower()
                self.assertNotIn("traceback", body)
                self.assertNotIn("django_secret_key", body)


class PaymentReconciliationTests(TestCase):
    def setUp(self):
        self.student = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(),
            email="payment-student@example.com",
            first_name="Payment",
            last_name="Student",
            academic_level="N4",
        )
        self.category = CourseCategory.objects.create(name="TVET", slug="tvet")
        self.course = Course.objects.create(
            category=self.category,
            title="Engineering Mathematics N4",
            slug="engineering-mathematics-n4",
            short_description="N4 revision",
            description="TVET N4 engineering mathematics.",
            curriculum="TVET",
            academic_level="N4",
            price=950,
            status=Course.Status.PUBLISHED,
        )

    def test_verified_payment_creates_enrollment_idempotently(self):
        now = timezone.now()
        payment = Payment.objects.create(
            reference=f"PAY-{uuid.uuid4()}",
            student=self.student,
            course=self.course,
            provider=Payment.Provider.PAYFAST,
            amount=950,
            status=Payment.Status.PAID,
            provider_reference=f"PF-{uuid.uuid4()}",
            paid_at=now,
            gateway_verified_at=now,
            verification_source="ci-test",
        )
        reconcile_verified_payments()
        reconcile_verified_payments()

        self.assertEqual(Enrollment.objects.filter(student=self.student, course=self.course).count(), 1)
        enrollment = Enrollment.objects.get(student=self.student, course=self.course)
        self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(payment.enrollment_id, enrollment.pk)

    def test_unverified_payment_does_not_create_enrollment(self):
        Payment.objects.create(
            reference=f"PAY-{uuid.uuid4()}",
            student=self.student,
            course=self.course,
            provider=Payment.Provider.PAYFAST,
            amount=950,
            status=Payment.Status.PAID,
            provider_reference=f"PF-{uuid.uuid4()}",
            paid_at=timezone.now(),
            gateway_verified_at=None,
        )
        reconcile_verified_payments()

        self.assertFalse(Enrollment.objects.filter(student=self.student, course=self.course).exists())


class StudentRecordTests(TestCase):
    def test_student_record_created_for_user(self):
        record = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(),
            email="student-record@example.com",
            first_name="Student",
            last_name="Record",
            academic_level="Grade 12",
        )
        self.assertEqual(record.email, "student-record@example.com")
        self.assertEqual(record.academic_level, "Grade 12")
