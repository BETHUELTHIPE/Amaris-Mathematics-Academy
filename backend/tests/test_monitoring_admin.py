from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse

from amaris_cms.monitoring_admin import AmarisAdminSite, MetricsAccessMiddleware


class MonitoringAdminTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.site = AmarisAdminSite()
        self.superuser = SimpleNamespace(
            is_authenticated=True, is_active=True, is_staff=True, is_superuser=True
        )
        self.staff = SimpleNamespace(
            is_authenticated=True, is_active=True, is_staff=True, is_superuser=False
        )

    def test_admin_route_exists(self):
        self.assertEqual(reverse("admin:amaris_monitoring_home"), "/admin/monitoring/")

    def test_staff_cannot_open_home_or_consoles(self):
        request = self.factory.get("/admin/monitoring/")
        request.user = self.staff
        with self.assertRaises(PermissionDenied):
            self.site.monitoring_home(request)
        with self.assertRaises(PermissionDenied):
            self.site.monitoring_console(request, "grafana")

    @override_settings(MONITORING_CONSOLE_ENABLED=False)
    def test_superuser_only_sees_unconfigured_when_disabled(self):
        request = self.factory.get("/admin/monitoring/grafana/")
        request.user = self.superuser
        self.assertEqual(self.site.monitoring_console(request, "grafana").status_code, 503)

    @override_settings(MONITORING_CONSOLE_ENABLED=True)
    def test_read_only_and_allowlisted_upstreams(self):
        request = self.factory.post("/admin/monitoring/grafana/api/admin/users")
        request.user = self.superuser
        self.assertEqual(self.site.monitoring_console(request, "grafana").status_code, 405)
        request = self.factory.get("/admin/monitoring/untrusted/")
        request.user = self.superuser
        self.assertEqual(self.site.monitoring_console(request, "untrusted").status_code, 404)

    @override_settings(MONITORING_CONSOLE_ENABLED=True)
    def test_traversal_is_rejected_before_network(self):
        request = self.factory.get("/admin/monitoring/grafana/a/b")
        request.user = self.superuser
        self.assertEqual(self.site.monitoring_console(request, "grafana", "../secrets").status_code, 404)

    @override_settings(MONITORING_CONSOLE_ENABLED=True)
    @patch("amaris_cms.monitoring_admin.urllib_request.build_opener")
    def test_proxy_does_not_forward_browser_cookies_or_credentials(self, opener_factory):
        class Reply:
            status = 200
            headers = {"Content-Type": "text/plain"}
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self, size):
                return b"up 1\n"
        opener_factory.return_value.open.return_value = Reply()
        request = self.factory.get("/admin/monitoring/prometheus/api/v1/query?query=up", HTTP_COOKIE="sessionid=secret", HTTP_AUTHORIZATION="Bearer attack")
        request.user = self.superuser
        result = self.site.monitoring_console(request, "prometheus", "api/v1/query")
        self.assertEqual(result.status_code, 200)
        req = opener_factory.return_value.open.call_args.args[0]
        self.assertNotIn("Cookie", req.headers)
        self.assertNotIn("Authorization", req.headers)
        self.assertEqual(req.full_url, "http://prometheus:9090/admin/monitoring/prometheus/api/v1/query?query=up")


class MetricsSecurityTests(SimpleTestCase):
    def setUp(self):
        self.middleware = MetricsAccessMiddleware(lambda request: HttpResponse("allowed"))
        self.factory = RequestFactory()

    @override_settings(DEBUG=False, MONITORING_METRICS_TOKEN_FILE="")
    @patch.dict("os.environ", {"MONITORING_METRICS_TOKEN": ""})
    def test_production_metrics_are_hidden_without_secret(self):
        self.assertEqual(self.middleware(self.factory.get("/metrics")).status_code, 404)

    @override_settings(DEBUG=False, MONITORING_METRICS_TOKEN_FILE="")
    @patch.dict("os.environ", {"MONITORING_METRICS_TOKEN": "private-monitor-token"})
    def test_metrics_require_exact_bearer_token(self):
        self.assertEqual(self.middleware(self.factory.get("/metrics/")).status_code, 404)
        request = self.factory.get("/metrics/", HTTP_AUTHORIZATION="Bearer private-monitor-token")
        self.assertEqual(self.middleware(request).status_code, 200)

    def test_non_metrics_requests_are_not_blocked(self):
        self.assertEqual(self.middleware(self.factory.get("/health/live/")).status_code, 200)
