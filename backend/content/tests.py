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
        response = self.client.get(reverse("admin:index"))
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
        response = self.client.get(reverse("courses-list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["results"][0]["slug"], "published-course")

    def test_site_settings_endpoint(self):
        SiteSettings.objects.create()
        response = self.client.get(reverse("site-settings"))
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

        first = self.client.get(reverse("courses-list"))
        payload = first.json()["results"][0]
        self.assertNotIn("modules", payload)
        self.assertNotIn("outcomes", payload)
        self.assertNotIn("description", payload)

        with self.assertNumQueries(0):
            second = self.client.get(reverse("courses-list"))
        self.assertEqual(second.content, first.content)


class PermissionTests(TestCase):
    def test_anonymous_and_non_staff_users_cannot_enter_admin(self):
        anonymous = self.client.get(reverse("admin:index"))
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn("/admin/login/", anonymous.headers["Location"])

        user = get_user_model().objects.create_user(
            username="student-test",
            email="student-test@example.com",
            password="Strong-Test-Password-123!",
        )
        self.client.force_login(user)
        non_staff = self.client.get(reverse("admin:index"))
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
            youtube_video_id="private-video-id",
            youtube_url="https://www.youtube.com/watch?v=private-video-id",
            is_published=True,
        )
        Lesson.objects.create(
            module=module,
            title="Factorisation",
            slug="factorisation",
            video=video,
            order=1,
            is_published=True,
        )

        response = self.client.get(reverse("courses-detail", kwargs={"slug": course.slug}))
        body = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("private-video-id", body)
        self.assertNotIn("youtube_url", body)
        self.assertNotIn("youtube_video_id", body)


class HealthAndMetricsTests(TestCase):
    def test_liveness_and_readiness_do_not_disclose_infrastructure(self):
        live = self.client.get(reverse("health-live"))
        ready = self.client.get(reverse("health-ready"))

        self.assertEqual(live.status_code, 200)
        self.assertEqual(live.json(), {"status": "ok"})
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(\n            ready.json(),\n            {"status": "ready", "version": {"git_sha": "unknown", "image_tag": "unknown"}},\n        )
        self.assertNotContains(live, "postgres", status_code=200)
        self.assertNotContains(ready, "redis", status_code=200)

    @patch("amaris_cms.urls.Redis.from_url", side_effect=ConnectionError)
    def test_redis_failure_degrades_dependencies_but_not_readiness(self, _redis):
        ready = self.client.get(reverse("health-ready"))
        dependencies = self.client.get(reverse("health-dependencies"))

        self.assertEqual(ready.status_code, 200)
        self.assertEqual(dependencies.status_code, 200)
        self.assertEqual(dependencies.json()["status"], "degraded")
        self.assertTrue(dependencies.json()["dependencies"]["postgresql"])
        self.assertFalse(dependencies.json()["dependencies"]["redis"])

    def test_prometheus_metrics_endpoint_is_available_to_private_scraper(self):
        response = self.client.get("/metrics")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response.headers["Content-Type"])


class ErrorRecoveryTests(TestCase):
    def test_branded_error_pages_are_safe_and_traceable(self):
        for status in (400, 403, 404, 429, 500):
            with self.subTest(status=status):
                response = self.client.get(reverse(f"error-{status}"))
                self.assertEqual(response.status_code, status)
                self.assertContains(response, "Amaris Mathematics Academy", status_code=status)
                self.assertContains(response, "Support reference", status_code=status)
                self.assertRegex(response.headers["X-Correlation-ID"], r"^AMR-[A-Z0-9-]+$")
                body = response.content.decode().lower()
                self.assertNotIn("traceback", body)
                self.assertNotIn("django_secret_key", body)


class PaymentReconciliationTests(TestCase):
    def setUp(self):
        category = CourseCategory.objects.create(name="University", slug="university")
        self.course = Course.objects.create(
            category=category,
            title="Calculus I",
            slug="calculus-i",
            short_description="Limits and derivatives",
            description="A complete introductory calculus course.",
            curriculum="University",
            academic_level="First year",
            price=1200,
            status=Course.Status.PUBLISHED,
        )
        self.student = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(),
            email="reconcile@example.com",
            first_name="Test",
            last_name="Student",
        )

    def payment(self, reference, verified):
        return Payment.objects.create(
            reference=reference,
            student=self.student,
            course=self.course,
            provider=Payment.Provider.PAYFAST,
            amount=self.course.price,
            status=Payment.Status.PAID,
            paid_at=timezone.now(),
            gateway_verified_at=timezone.now() if verified else None,
            verification_source="payfast_itn" if verified else "",
        )

    def test_unverified_paid_record_never_activates_access(self):
        self.payment("UNVERIFIED-1", verified=False)

        run = reconcile_verified_payments()

        self.assertEqual(Enrollment.objects.count(), 0)
        self.assertEqual(run.unresolved_count, 1)

    def test_verified_payment_repairs_access_exactly_once(self):
        payment = self.payment("VERIFIED-1", verified=True)

        first = reconcile_verified_payments()
        second = reconcile_verified_payments()

        enrollment = Enrollment.objects.get(student=self.student, course=self.course)
        payment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)
        self.assertEqual(payment.enrollment, enrollment)
        self.assertEqual(Enrollment.objects.count(), 1)
        self.assertEqual(first.enrollments_repaired, 1)
        self.assertEqual(second.enrollments_repaired, 0)

    def test_cancelled_access_is_not_silently_reactivated(self):
        enrollment = Enrollment.objects.create(
            student=self.student,
            course=self.course,
            status=Enrollment.Status.CANCELLED,
        )
        self.payment("VERIFIED-CANCELLED", verified=True)

        run = reconcile_verified_payments()

        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.CANCELLED)
        self.assertEqual(run.unresolved_count, 1)
