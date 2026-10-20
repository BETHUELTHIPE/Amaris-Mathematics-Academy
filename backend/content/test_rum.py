import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from content.models import WebVitalBucket
from content.rum import bucket_for, summarize_p75


@override_settings(
    RUM_INGEST_TOKEN="test-only-rum-token-not-production", RUM_PERSIST_ENABLED=True, SECURE_SSL_REDIRECT=False
)
class WebVitalsCollectionTests(TestCase):
    def setUp(self):
        self.url = reverse("anonymous-web-vitals")
        self.headers = {
            "HTTP_X_AMARIS_RUM_TOKEN": "test-only-rum-token-not-production",
            "HTTP_X_AMARIS_RUM_RELEASE": "abcdef012345",
        }
        self.valid = {"name": "LCP", "value": 2250, "route": "courses", "device": "mobile", "network": "3g"}

    def send(self, records, **kwargs):
        with patch("content.rum.secrets.randbelow", return_value=99):
            return self.client.post(
                self.url,
                data=json.dumps({"records": records}),
                content_type="application/json",
                **kwargs,
            )

    def test_disabled_persistence_refuses_ingestion(self):
        with override_settings(RUM_PERSIST_ENABLED=False):
            self.assertEqual(self.send([self.valid], **self.headers).status_code, 503)
        self.assertEqual(WebVitalBucket.objects.count(), 0)

    def test_invalid_release_is_rejected(self):
        self.assertEqual(
            self.send(
                [self.valid],
                HTTP_X_AMARIS_RUM_TOKEN="test-only-rum-token-not-production",
                HTTP_X_AMARIS_RUM_RELEASE="../private",
            ).status_code,
            400,
        )
        self.assertEqual(WebVitalBucket.objects.count(), 0)

    def test_requires_server_only_secret(self):
        self.assertEqual(self.send([self.valid]).status_code, 403)
        with override_settings(RUM_INGEST_TOKEN=""):
            self.assertEqual(self.send([self.valid], **self.headers).status_code, 403)
        self.assertEqual(WebVitalBucket.objects.count(), 0)

    def test_aggregates_counters_without_identifiers(self):
        self.assertEqual(self.send([self.valid], **self.headers).status_code, 204)
        self.assertEqual(self.send([self.valid], **self.headers).status_code, 204)
        row = WebVitalBucket.objects.get()
        self.assertEqual(row.count, 2)
        self.assertEqual(row.release, "abcdef012345")
        self.assertEqual(row.bucket, bucket_for("LCP", 2250))
        self.assertFalse(hasattr(row, "student_id"))
        self.assertFalse(hasattr(row, "user_agent"))
        self.assertFalse(hasattr(row, "ip_address"))

    def test_only_approved_routes_and_values_are_stored(self):
        for record in (
            {**self.valid, "route": "/student/42/payments?token=secret"},
            {**self.valid, "account": "student@example.test"},
            {**self.valid, "value": -10},
            {**self.valid, "value": True},
            {**self.valid, "value": float("nan")},
            {**self.valid, "network": "wifi SSID abc"},
        ):
            self.assertEqual(self.send([record], **self.headers).status_code, 400)
        self.assertEqual(WebVitalBucket.objects.count(), 0)

    def test_rejects_unbounded_payload_and_non_post(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(self.send([self.valid] * 4, **self.headers).status_code, 400)
        self.assertEqual(
            self.client.post(self.url, data="x" * 2000, content_type="application/json", **self.headers).status_code,
            400,
        )

    def test_p75_is_coarse_and_suppresses_small_cohorts(self):
        for i in range(20):
            self.assertEqual(
                self.send([{**self.valid, "value": 1700 if i < 15 else 2800}], **self.headers).status_code,
                204,
            )
        summary = summarize_p75(days=28)
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["samples"], 20)
        self.assertEqual(summary[0]["p75_bound"], 2000)
        self.assertEqual(summarize_p75(days=28, min_samples=21), [])
        WebVitalBucket.objects.update(day=timezone.now().date() - timedelta(days=40))
        self.assertEqual(summarize_p75(days=28), [])

    def test_ingest_does_not_require_student_authentication(self):
        User = get_user_model()
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(self.send([self.valid], **self.headers).status_code, 204)


@override_settings(SECURE_SSL_REDIRECT=False)
class WebVitalsAdminTests(TestCase):
    def test_only_superuser_may_view_aggregates_or_p75_report(self):
        User = get_user_model()
        superuser = User.objects.create_superuser("rum_admin", "admin@example.test", "test-password")
        staff = User.objects.create_user("rum_staff", "staff@example.test", "test-password", is_staff=True)
        path = reverse("admin:content_webvitalbucket_report")
        self.client.force_login(staff)
        self.assertNotEqual(self.client.get(path).status_code, 200)
        self.client.force_login(superuser)
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Anonymous real-user performance")

    def test_admin_suppresses_small_cohorts(self):
        User = get_user_model()
        admin = User.objects.create_superuser("rum_admin", "admin@example.test", "test-password")
        self.client.force_login(admin)
        WebVitalBucket.objects.create(
            day=timezone.now().date(),
            metric="INP",
            route="student",
            network="3g",
            device="mobile",
            bucket=3,
            count=1,
        )
        response = self.client.get(reverse("admin:content_webvitalbucket_report"))
        self.assertContains(response, "No group has at least 20 observations")
        self.assertNotContains(response, "<td>student</td>")
