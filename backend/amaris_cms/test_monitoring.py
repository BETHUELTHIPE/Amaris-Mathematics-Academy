from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .monitoring import validate_monitoring_url


@override_settings(
    ADMIN_MONITORING_URLS={
        "flower": "/monitoring/flower/",
        "prometheus": "/monitoring/prometheus/",
        "grafana": "https://grafana.example.com/",
        "cadvisor": "/monitoring/cadvisor/",
    }
)
class MonitoringAdminTests(TestCase):
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

    def test_superuser_gets_all_four_configured_links(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:monitoring"), secure=True)
        self.assertEqual(response.status_code, 200)
        for label in ("Flower", "Prometheus", "Grafana", "cAdvisor"):
            self.assertContains(response, f"Open {label}")
        self.assertContains(response, 'href="https://grafana.example.com/"')
        self.assertContains(response, 'rel="noopener noreferrer"', count=4)
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
        self.assertContains(response, "Connection not configured.", count=4)
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
