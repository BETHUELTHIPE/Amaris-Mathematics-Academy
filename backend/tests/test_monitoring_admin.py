from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse

from amaris_cms.monitoring_admin import AmarisAdminSite


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

    @override_settings(
        MONITORING_CONSOLE_ENABLED=True,
        MONITORING_GRAFANA_URL="http://grafana-private:10000",
    )
    @patch("amaris_cms.monitoring_admin.urllib_request.build_opener")
    def test_superuser_same_origin_grafana_query_post_is_read_only_forwarded(self, opener_factory):
        class Reply:
            status = 200
            headers = {"Content-Type": "application/json"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self, size):
                return b'{"results":{}}'

        opener_factory.return_value.open.return_value = Reply()
        request = self.factory.post(
            "/admin/monitoring/grafana/api/ds/query",
            data='{"queries":[{"datasource":{"uid":"amaris-pg-staging"},"rawSql":"select 1"}]}',
            content_type="application/json",
            HTTP_ORIGIN="http://testserver",
            HTTP_COOKIE="sessionid=do-not-forward",
        )
        request.user = self.superuser
        response = self.site.monitoring_console(request, "grafana", "api/ds/query")
        self.assertEqual(response.status_code, 200)
        outbound = opener_factory.return_value.open.call_args.args[0]
        self.assertEqual(outbound.get_method(), "POST")
        self.assertEqual(outbound.data, b'{"queries":[{"datasource":{"uid":"amaris-pg-staging"},"rawSql":"select 1"}]}')
        self.assertNotIn("Cookie", outbound.headers)
        self.assertEqual(outbound.full_url, "http://grafana-private:10000/admin/monitoring/grafana/api/ds/query")

    @override_settings(
        MONITORING_CONSOLE_ENABLED=True,
        MONITORING_GRAFANA_URL="http://grafana-private:10000",
    )
    def test_grafana_post_rejects_cross_origin_and_unprivileged_users(self):
        bad_origin = self.factory.post(
            "/admin/monitoring/grafana/api/ds/query",
            data='{"queries":[{"datasource":{"uid":"amaris-pg-staging"},"rawSql":"select 1"}]}',
            content_type="application/json",
            HTTP_ORIGIN="https://another.example",
        )
        bad_origin.user = self.superuser
        self.assertEqual(self.site.monitoring_console(bad_origin, "grafana", "api/ds/query").status_code, 403)

        denied = self.factory.post(
            "/admin/monitoring/grafana/api/ds/query",
            data='{"queries":[{"datasource":{"uid":"amaris-pg-staging"},"rawSql":"select 1"}]}',
            content_type="application/json",
            HTTP_ORIGIN="http://testserver",
        )
        denied.user = self.staff
        with self.assertRaises(PermissionDenied):
            self.site.monitoring_console(denied, "grafana", "api/ds/query")
