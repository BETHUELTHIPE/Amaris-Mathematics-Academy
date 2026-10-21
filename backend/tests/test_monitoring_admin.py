import json
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve, reverse

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

    @patch("django.contrib.admin.AdminSite.get_app_list", return_value=[])
    def test_sidebar_links_are_superuser_only(self, app_list):
        request = self.factory.get("/admin/")
        request.user = self.superuser
        links = self.site.get_app_list(request)[0]["models"]
        self.assertEqual([link["name"] for link in links], ["Grafana", "Prometheus", "Flower"])
        self.assertEqual(links[0]["admin_url"], "/admin/monitoring/grafana/")
        self.assertEqual(self.site.get_app_list(request, "content"), [])
        request.user = self.staff
        self.assertEqual(self.site.get_app_list(request), [])

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


@override_settings(
    MONITORING_CONSOLE_ENABLED=True,
    MONITORING_GRAFANA_URL="http://grafana-private:10000",
    ALLOWED_HOSTS=["testserver"],
)
class GrafanaQueryTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = SimpleNamespace(is_authenticated=True, is_active=True, is_staff=True, is_superuser=True)
        self.payload = {"queries": [{"refId": "A", "datasource": {"uid": "amaris-prometheus"}, "expr": "up"}]}

    def request(self, payload=None, **headers):
        request = self.factory.post(
            "/admin/monitoring/grafana/api/ds/query",
            data=json.dumps(self.payload if payload is None else payload),
            content_type="application/json",
            secure=True,
            **{"HTTP_ORIGIN": "https://testserver", **headers},
        )
        request.user = self.user
        return request

    @patch("amaris_cms.monitoring_admin.urllib_request.build_opener")
    def test_native_grafana_query_works_without_django_csrf_token(self, opener_factory):
        from unittest.mock import MagicMock

        reply = MagicMock(status=200, headers={"Content-Type": "application/json"})
        reply.__enter__.return_value = reply
        reply.read.return_value = b'{"results":{"A":{}}}'
        opener_factory.return_value.open.return_value = reply
        request = self.request(HTTP_COOKIE="sessionid=private", HTTP_AUTHORIZATION="Bearer private")
        view = resolve(request.path).func
        self.assertTrue(view.csrf_exempt)
        response = view(request)
        self.assertEqual(response.status_code, 200)
        outbound = opener_factory.return_value.open.call_args.args[0]
        self.assertEqual(outbound.method, "POST")
        self.assertEqual(json.loads(outbound.data), self.payload)
        self.assertEqual(outbound.get_header("Content-type"), "application/json")
        self.assertNotIn("Cookie", outbound.headers)
        self.assertNotIn("Authorization", outbound.headers)

    @patch("amaris_cms.monitoring_admin.urllib_request.build_opener")
    def test_cross_origin_or_missing_origin_queries_are_denied(self, opener_factory):
        for origin in ("https://attacker.example", "http://testserver", "null", "", "http://["):
            with self.subTest(origin=origin):
                with self.assertRaises(PermissionDenied):
                    resolve("/admin/monitoring/grafana/api/ds/query").func(self.request(HTTP_ORIGIN=origin))
        opener_factory.assert_not_called()

    def test_same_origin_referer_is_supported(self):
        request = self.request(HTTP_ORIGIN="", HTTP_REFERER="https://testserver/admin/monitoring/grafana/d/dashboard")
        request._body = b"{}"
        self.assertEqual(resolve(request.path).func(request).status_code, 400)

    def test_non_superuser_query_is_denied(self):
        request = self.request()
        request.user.is_superuser = False
        with self.assertRaises(PermissionDenied):
            resolve(request.path).func(request)

    @patch("amaris_cms.monitoring_admin.urllib_request.build_opener")
    def test_invalid_or_other_datasource_queries_never_reach_upstream(self, opener_factory):
        for payload in ([], {}, {"queries": []}, {"queries": [None]}, {"queries": [{"datasource": {"uid": "other"}}]}):
            with self.subTest(payload=payload):
                request = self.request(payload)
                self.assertEqual(resolve(request.path).func(request).status_code, 400)
        request = self.request()
        request._body = b"not json"
        self.assertEqual(resolve(request.path).func(request).status_code, 400)
        request = self.request()
        request.META["CONTENT_LENGTH"] = str(256 * 1024 + 1)
        self.assertEqual(resolve(request.path).func(request).status_code, 413)
        request = self.request()
        request.content_type = "text/plain"
        self.assertEqual(resolve(request.path).func(request).status_code, 415)
        opener_factory.assert_not_called()

    def test_query_exception_does_not_allow_mutations(self):
        for tool, subpath in (
            ("grafana", "api/dashboards/db"),
            ("grafana", "api/admin/users"),
            ("flower", "api/worker/shutdown"),
        ):
            request = self.request()
            self.assertEqual(AmarisAdminSite().monitoring_console(request, tool, subpath).status_code, 405)
        self.assertFalse(getattr(resolve("/admin/monitoring/grafana/api/admin/users").func, "csrf_exempt", False))


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
        def inspect_target(url):
            if url.endswith("/admin/monitoring/flower/"):
                return (200, b"<html>flower</html>")
            if url.endswith("/admin/monitoring/flower/api/workers?status=true"):
                return (200, b'{"celery-worker-test": true}')
            return (200, b"render_metrics_exporter_refresh_success 0\\n")

        request_probe.side_effect = inspect_target
        items = {r["name"]: r for r in monitor_statuses()}
        self.assertEqual(items["grafana"]["status"], "unconfigured")
        self.assertEqual(items["prometheus"]["status"], "unconfigured")
        self.assertEqual(items["flower"]["status"], "reachable")
        self.assertEqual(items["render"]["status"], "degraded")

    @override_settings(
        MONITORING_CONSOLE_ENABLED=True,
        MONITORING_GRAFANA_URL="",
        MONITORING_PROMETHEUS_URL="",
        MONITORING_FLOWER_URL="http://amaris-monitoring-flower:10000",
        MONITORING_RENDER_EXPORTER_URL="",
    )
    @patch("amaris_cms.monitoring_status._request")
    def test_flower_ui_without_live_workers_is_degraded(self, request_probe):
        def inspect_target(url):
            if url.endswith("/admin/monitoring/flower/"):
                return (200, b"<html>Flower</html>")
            if url.endswith("/admin/monitoring/flower/api/workers?status=true"):
                return (200, b"{}")
            raise AssertionError("Unexpected probe target")

        request_probe.side_effect = inspect_target
        items = {record["name"]: record for record in monitor_statuses()}
        self.assertEqual(items["flower"]["status"], "degraded")

    @patch("amaris_cms.monitoring_status._request")
    def test_cached_or_expired_flower_workers_never_report_live(self, request_probe):
        for payload in (b'{"worker": false}', b'{"worker": {"status": true}}', b'{"worker": "true"}'):
            with self.subTest(payload=payload):
                _probe.cache_clear()
                request_probe.side_effect = [(200, b"Flower"), (200, payload)]
                self.assertEqual(_probe("flower", "http://flower:5555", 1), "degraded")

    @override_settings(MONITORING_FLOWER_BASIC_AUTH="synthetic:test-secret")
    @patch("amaris_cms.monitoring_status.urllib_request.build_opener")
    def test_flower_worker_probe_forwards_only_server_held_basic_auth(self, opener_factory):
        class Reply:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self, size):
                return b"{}"

        opener_factory.return_value.open.return_value = Reply()
        from amaris_cms.monitoring_status import _request

        _request("http://amaris-monitoring-flower:10000/admin/monitoring/flower/api/workers")
        request = opener_factory.return_value.open.call_args.args[0]
        self.assertIn("Authorization", request.headers)
        self.assertNotIn("Cookie", request.headers)

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
