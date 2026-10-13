import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .monitoring import MONITORING_DASHBOARDS, monitoring_urls, validate_monitoring_url


@override_settings(
    ADMIN_MONITORING_URLS={
        "flower": "/monitoring/flower/",
        "prometheus": "/monitoring/prometheus/",
        "grafana": "https://grafana.example.com/",
        "cadvisor": "/monitoring/cadvisor/",
        "alertmanager": "/monitoring/alertmanager/",
    }
)
class MonitoringAdminTests(TestCase):
    superuser: User
    staff: User

    @classmethod
    def setUpTestData(cls):
        cls.superuser = get_user_model().objects.create_superuser(
            "monitor-admin", "monitor@example.com", "test-password"
        )
        cls.staff = get_user_model().objects.create_user("monitor-staff", is_staff=True)

    def test_anonymous_console_page_redirects_to_login(self):
        response = self.client.get(reverse("admin:monitoring"), secure=True)
        self.assertRedirects(response, "/admin/login/?next=/admin/monitoring/", fetch_redirect_response=False)

    def test_regular_staff_cannot_access_infrastructure_consoles(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("admin:monitoring"), secure=True).status_code, 403)
        self.assertEqual(self.client.get(reverse("monitoring-access"), secure=True).status_code, 403)

    def test_superuser_gets_every_console_and_infrastructure_dashboard(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:monitoring"), secure=True)
        self.assertEqual(response.status_code, 200)
        for label in (
            "Flower",
            "Prometheus",
            "Grafana",
            "cAdvisor",
            "Alertmanager",
            "PostgreSQL",
            "Redis broker",
            "Redis cache",
            "Docker host",
            "Website uptime",
        ):
            self.assertContains(response, f"Open {label}")
        self.assertContains(response, 'href="https://grafana.example.com/"')
        self.assertContains(response, 'href="https://grafana.example.com/d/amaris-postgresql/amaris-postgresql"')
        self.assertContains(response, 'rel="noopener noreferrer"', count=10)
        self.assertIn("no-store", response["Cache-Control"])

    def test_admin_home_exposes_monitoring_entry(self):
        self.client.force_login(self.superuser)
        self.assertContains(self.client.get(reverse("admin:index"), secure=True), reverse("admin:monitoring"))

    def test_unconfigured_service_has_no_broken_link(self):
        self.client.force_login(self.superuser)
        with override_settings(
            ADMIN_MONITORING_URLS=dict.fromkeys(("flower", "prometheus", "grafana", "cadvisor"), "")
        ):
            response = self.client.get(reverse("admin:monitoring"), secure=True)
        self.assertContains(response, "Connection not configured.", count=5)
        self.assertContains(response, "Grafana connection not configured.", count=5)
        self.assertNotContains(response, 'class="btn btn-primary"')

    def test_auth_subrequest_returns_status_and_does_not_cache_sessions(self):
        url = reverse("monitoring-access")
        response = self.client.get(url, secure=True)
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("Location", response)
        self.assertIn("no-store", response["Cache-Control"])
        self.client.force_login(self.superuser)
        response = self.client.get(url, secure=True)
        self.assertEqual(response.status_code, 204)
        self.assertIn("Cookie", response["Vary"])
        self.superuser.is_active = False
        self.superuser.save(update_fields=["is_active"])
        self.assertNotEqual(self.client.get(url, secure=True).status_code, 204)


class MonitoringUrlTests(SimpleTestCase):
    def test_one_host_configures_all_consoles_with_individual_overrides(self):
        urls = monitoring_urls("https://monitor.example.com/", False, {"grafana": "https://grafana.example.com/"})
        self.assertEqual(urls["alertmanager"], "https://monitor.example.com/monitoring/alertmanager/")
        self.assertEqual(urls["flower"], "https://monitor.example.com/monitoring/flower/")
        self.assertEqual(urls["grafana"], "https://grafana.example.com/")

    def test_base_url_rejects_ambiguous_query_or_fragment(self):
        for value in ("https://monitor.example.com/?token=value", "https://monitor.example.com/#fragment"):
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured):
                monitoring_urls(value, False, {})

    def test_each_admin_dashboard_has_a_provisioned_grafana_dashboard(self):
        directory = Path(__file__).resolve().parent.parent / "monitoring" / "grafana" / "dashboards"
        dashboards = {data["uid"]: data for path in directory.glob("*.json") if (data := json.loads(path.read_text()))}
        for *_, uid in MONITORING_DASHBOARDS:
            with self.subTest(dashboard=uid):
                self.assertIn(uid, dashboards)
                self.assertTrue(dashboards[uid]["panels"])
                for panel in dashboards[uid]["panels"]:
                    self.assertEqual(panel["datasource"]["uid"], "prometheus")
                    self.assertTrue(panel["targets"][0]["expr"])

    def test_allows_https_and_root_relative_console_urls(self):
        for value in (
            "",
            "/monitoring/grafana/",
            "https://grafana.example.com/",
            "http://localhost:8080/monitoring/flower/",
        ):
            self.assertEqual(validate_monitoring_url(value), value)

    def test_rejects_scripts_credentials_and_ambiguous_urls(self):
        for value in (
            "javascript:alert(1)",
            "//evil.example.com/",
            "https://user:password@example.com/",
            "https://example.com/a\nb",
            "/\\evil.example.com/",
            "http://[broken",
        ):
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured):
                validate_monitoring_url(value)
