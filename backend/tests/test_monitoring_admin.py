from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse

from amaris_cms.monitoring_admin import AmarisAdminSite
from amaris_cms.monitoring_status import _probe, is_private_monitoring_url, monitor_statuses


class MonitoringAdminTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.site = AmarisAdminSite()
        self.superuser = SimpleNamespace(
            is_authenticated=True,
            is_active=True,
            is_staff=True,
            is_superuser=True,
        )
        self.staff = SimpleNamespace(
            is_authenticated=True,
            is_active=True,
            is_staff=True,
            is_superuser=False,
        )

    def test_admin_route_exists(self):
        self.assertEqual(reverse("admin:amaris_monitoring_home"), "/admin/monitoring/")

    def test_non_superuser_is_denied(self):
        request = self.factory.get("/admin/monitoring/")
        request.user = self.staff
        with self.assertRaises(PermissionDenied):
            self.site.monitoring_home(request)

    @override_settings(MONITORING_CONSOLE_ENABLED=False)
    def test_disabled_monitoring_returns_503(self):
        request = self.factory.get("/admin/monitoring/grafana/")
        request.user = self.superuser
        self.assertEqual(self.site.monitoring_console(request, "grafana").status_code, 503)

    @override_settings(
        MONITORING_CONSOLE_ENABLED=True,
        MONITORING_GRAFANA_URL="http://grafana-private:10000",
        MONITORING_PROMETHEUS_URL="http://prometheus-private:10000",
        MONITORING_FLOWER_URL="http://flower-private:10000",
    )
    def test_proxy_is_read_only_and_allowlisted(self):
        request = self.factory.post("/admin/monitoring/grafana/api/admin/users")
        request.user = self.superuser
        self.assertEqual(self.site.monitoring_console(request, "grafana").status_code, 405)

        request = self.factory.get("/admin/monitoring/untrusted/")
        request.user = self.superuser
        self.assertEqual(self.site.monitoring_console(request, "untrusted").status_code, 404)

    @override_settings(
        MONITORING_CONSOLE_ENABLED=True,
        MONITORING_GRAFANA_URL="http://grafana-private:10000",
        MONITORING_PROMETHEUS_URL="http://prometheus-private:10000",
        MONITORING_FLOWER_URL="http://flower-private:10000",
    )
    @patch("amaris_cms.monitoring_admin.urllib_request.build_opener")
    def test_proxy_does_not_forward_browser_credentials(self, opener_factory):
        class Reply:
            status = 200
            headers = {"Content-Type": "text/plain"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self, size):
                return b"up 1\n"

        opener_factory.return_value.open.return_value = Reply()
        request = self.factory.get(
            "/admin/monitoring/prometheus/api/v1/query?query=up",
            HTTP_COOKIE="sessionid=secret",
            HTTP_AUTHORIZATION="Bearer attack",
        )
        request.user = self.superuser

        response = self.site.monitoring_console(
            request,
            "prometheus",
            "api/v1/query",
        )
        self.assertEqual(response.status_code, 200)

        outbound = opener_factory.return_value.open.call_args.args[0]
        self.assertNotIn("Cookie", outbound.headers)
        self.assertNotIn("Authorization", outbound.headers)
        self.assertEqual(
            outbound.full_url,
            "http://prometheus-private:10000/admin/monitoring/prometheus/api/v1/query?query=up",
        )


class RealMonitoringStatusTests(SimpleTestCase):
    def setUp(self):
        _probe.cache_clear()

    def tearDown(self):
        _probe.cache_clear()

    def test_monitoring_url_validation_never_allows_credentials_or_unknown_paths(self):
        self.assertTrue(is_private_monitoring_url("http://amaris-monitoring-flower:10000"))
        self.assertTrue(is_private_monitoring_url("http://grafana:3000"))
        for candidate in (
            "http://user:secret@flower:5555",
            "https://flower.private/path",
            "http://flower:5555/path",
            "file:///etc/passwd",
            "http://flower:5555/?url=http://evil.example",
            "http://flower:bad",
            "http://flower:70000",
        ):
            self.assertFalse(is_private_monitoring_url(candidate))

    @override_settings(
        MONITORING_CONSOLE_ENABLED=True,
        MONITORING_GRAFANA_URL="",
        MONITORING_PROMETHEUS_URL="",
        MONITORING_FLOWER_URL="http://amaris-monitoring-flower:10000",
        MONITORING_RENDER_EXPORTER_URL="http://amaris-monitoring-render-metrics:10000",
    )
    @patch("amaris_cms.monitoring_status._request")
    def test_each_monitor_reports_actual_status_not_invented_online(self, request_probe):
        request_probe.side_effect = [
            (200, b"<html>flower</html>"),
            (
                200,
                b"# HELP render_metrics_exporter_refresh_success one\n" b"render_metrics_exporter_refresh_success 0\n",
            ),
        ]
        items = {r["name"]: r for r in monitor_statuses()}
        self.assertEqual(items["grafana"]["status"], "unconfigured")
        self.assertEqual(items["prometheus"]["status"], "unconfigured")
        self.assertEqual(items["flower"]["status"], "reachable")
        self.assertEqual(items["render"]["status"], "degraded")

    @override_settings(
        MONITORING_CONSOLE_ENABLED=False,
        MONITORING_GRAFANA_URL="http://grafana:3000",
        MONITORING_PROMETHEUS_URL="http://prometheus:9090",
        MONITORING_FLOWER_URL="http://flower:5555",
        MONITORING_RENDER_EXPORTER_URL="http://exporter:10000",
    )
    @patch("amaris_cms.monitoring_status._request")
    def test_disabled_monitoring_never_probes_private_network(self, request_probe):
        for item in monitor_statuses():
            self.assertEqual(item["status"], "unconfigured")
        request_probe.assert_not_called()

    @override_settings(
        MONITORING_CONSOLE_ENABLED=True,
        MONITORING_GRAFANA_URL="http://grafana:3000",
        MONITORING_PROMETHEUS_URL="",
        MONITORING_FLOWER_URL="",
        MONITORING_RENDER_EXPORTER_URL="",
    )
    @patch("amaris_cms.monitoring_status._request", return_value=(200, b"ok"))
    def test_live_only_when_server_really_responds(self, request_probe):
        response = {record["name"]: record for record in monitor_statuses()}
        self.assertEqual(response["grafana"]["status"], "reachable")
        self.assertEqual(response["prometheus"]["status"], "unconfigured")
        self.assertTrue(request_probe.called)

    @override_settings(
        MONITORING_CONSOLE_ENABLED=True,
        MONITORING_GRAFANA_URL="http://user:secret@grafana:3000",
        MONITORING_PROMETHEUS_URL="",
        MONITORING_FLOWER_URL="",
        MONITORING_RENDER_EXPORTER_URL="",
    )
    def test_invalid_proxy_upstream_is_denied(self):
        site = AmarisAdminSite()
        factory = RequestFactory()
        request = factory.get("/admin/monitoring/grafana/")
        request.user = SimpleNamespace(is_authenticated=True, is_active=True, is_staff=True, is_superuser=True)
        self.assertEqual(site.monitoring_console(request, "grafana").status_code, 503)
