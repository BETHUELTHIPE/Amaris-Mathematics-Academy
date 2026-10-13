"""Admin monitoring security, Prometheus integration and graceful degradation."""

import json
import os
from unittest.mock import patch
from urllib.error import URLError

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from amaris_cms.monitoring_views import _safe_url


class AdminMonitoringTests(TestCase):
    def setUp(self):
        model = get_user_model()
        self.superuser = model.objects.create_superuser(
            username="monitor_admin", email="monitor@example.test", password="not-a-production-password-123"
        )
        self.staff = model.objects.create_user(
            username="monitor_staff", email="staff@example.test", password="not-a-production-password-456", is_staff=True
        )
        self.url = reverse("admin-monitoring")

    def test_anonymous_is_redirected_to_admin_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_staff_without_superuser_privileges_is_denied(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_unconfigured_services_do_not_look_healthy(self):
        self.client.force_login(self.superuser)
        with patch.dict(os.environ, {
            "PROMETHEUS_API_URL": "",
            "GRAFANA_DASHBOARD_URL": "",
            "FLOWER_DASHBOARD_URL": "",
            "CADVISOR_DASHBOARD_URL": "",
        }):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Monitoring and reliability")
        self.assertContains(response, "Not configured")
        self.assertContains(response, "Requests per second")
        self.assertNotContains(response, "Last Prometheus scrape succeeded.")
        self.assertIn("no-store", response["Cache-Control"])

    def test_live_queries_never_render_private_tokens(self):
        self.client.force_login(self.superuser)

        class FakeResponse:
            status = 200

            def __init__(self, contents):
                self.contents = contents

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, length):
                return self.contents[:length]

        def fake_urlopen(request, timeout):
            self.assertEqual(timeout, 2.5)
            self.assertEqual(request.get_header("Authorization"), "Bearer monitoring-secret-not-to-show")
            url = request.full_url
            if "query=up" in url:
                data = [
                    {"metric": {"job": "django"}, "value": [1, "1"]},
                    {"metric": {"job": "flower"}, "value": [1, "0"]},
                ]
            else:
                data = [{"metric": {}, "value": [1, "2.25"]}]
            return FakeResponse(
                json.dumps({"status": "success", "data": {"resultType": "vector", "result": data}}).encode()
            )

        with (
            patch.dict(
                os.environ,
                {
                    "PROMETHEUS_API_URL": "http://prometheus:9090",
                    "PROMETHEUS_API_BEARER_TOKEN": "monitoring-secret-not-to-show",
                    "GRAFANA_DASHBOARD_URL": "https://grafana.example.test/d/overview",
                    "FLOWER_DASHBOARD_URL": "",
                },
            ),
            patch("amaris_cms.monitoring_views.urlopen", side_effect=fake_urlopen),
        ):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Last Prometheus scrape succeeded.")
        self.assertContains(response, "Last Prometheus scrape failed.")
        self.assertContains(response, "2.25")
        self.assertContains(response, "https://grafana.example.test/d/overview")
        self.assertNotContains(response, "monitoring-secret-not-to-show")
        self.assertNotContains(response, "http://prometheus:9090")

    def test_collector_timeout_is_not_reported_as_healthy(self):
        self.client.force_login(self.superuser)
        with (
            patch.dict(os.environ, {"PROMETHEUS_API_URL": "http://prometheus:9090"}),
            patch("amaris_cms.monitoring_views.urlopen", side_effect=URLError("never reveal private host")),
        ):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Monitoring collector is unavailable.")
        self.assertNotContains(response, "never reveal private host")

    def test_unsafe_monitor_links_rejected(self):
        for value in ("javascript:alert(1)", "data:text/html,test", "https://user:password@example.com", "bad"):
            self.assertEqual(_safe_url(value), "")
        self.assertEqual(_safe_url("http://localhost:3000", allow_http=False), "")
        self.assertEqual(_safe_url("https://grafana.example.test/d/overview", allow_http=False),
                         "https://grafana.example.test/d/overview")
