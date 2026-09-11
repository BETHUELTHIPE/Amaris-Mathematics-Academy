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


# Existing test classes omitted here are unchanged in repository history.
# The health/recovery tests below use secure=True so production HTTPS redirect
# remains enabled while CI exercises the intended endpoint behaviour.


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
