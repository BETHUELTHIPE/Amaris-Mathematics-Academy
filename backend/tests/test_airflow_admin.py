from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from amaris_cms.airflow_client import (
    AirflowUnavailable,
    get_airflow_ui_url,
    get_workflow,
    get_workflow_tasks,
    is_configured,
)
from amaris_cms.monitoring_admin import AmarisAdminSite

AIRFLOW_TEST_SETTINGS = {
    "DEBUG": False,
    "AIRFLOW_MONITORING_ENABLED": True,
    "AIRFLOW_API_BASE_URL": "https://private-airflow.example.internal",
    "AIRFLOW_API_TOKEN": "test-only-token",
    "AIRFLOW_MONITORED_DAGS": ["amaris_service_health"],
}


class AirflowMonitorTests(SimpleTestCase):
    def setUp(self):
        self.site = AmarisAdminSite()
        self.factory = RequestFactory()
        self.superuser = SimpleNamespace(is_authenticated=True, is_active=True, is_staff=True, is_superuser=True)
        self.staff = SimpleNamespace(is_authenticated=True, is_active=True, is_staff=True, is_superuser=False)

    def test_routes_are_admin_only(self):
        self.assertEqual(reverse("admin:amaris_airflow_home"), "/admin/airflow/")
        self.assertEqual(
            reverse("admin:amaris_airflow_detail", kwargs={"dag_id": "amaris_service_health"}),
            "/admin/airflow/amaris_service_health/",
        )
        request = self.factory.get("/admin/airflow/")
        request.user = self.staff
        with self.assertRaises(PermissionDenied):
            self.site.airflow_home(request)

    @override_settings(**AIRFLOW_TEST_SETTINGS)
    @patch("amaris_cms.monitoring_admin.get_workflow")
    def test_superuser_sees_only_allowlisted_workflows(self, fetch):
        fetch.return_value = {"dag_id": "amaris_service_health", "state": "success"}
        request = self.factory.get("/admin/airflow/")
        request.user = self.superuser
        response = self.site.airflow_home(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context_data["workflows"][0]["state"], "success")
        fetch.assert_called_once_with("amaris_service_health")

        request = self.factory.get("/admin/airflow/arbitrary/")
        request.user = self.superuser
        self.assertEqual(self.site.airflow_detail(request, "arbitrary").status_code, 404)

    @override_settings(**AIRFLOW_TEST_SETTINGS)
    @patch("amaris_cms.monitoring_admin.get_workflow_tasks")
    def test_read_only_detail(self, fetch):
        fetch.return_value = (
            {"dag_id": "amaris_service_health", "state": "running"},
            [{"task_id": "check_backend", "state": "success"}],
        )
        request = self.factory.get("/admin/airflow/amaris_service_health/")
        request.user = self.superuser
        response = self.site.airflow_detail(request, "amaris_service_health")
        self.assertEqual(response.context_data["tasks"][0]["task_id"], "check_backend")
        fetch.assert_called_once()

        request = self.factory.post("/admin/airflow/amaris_service_health/")
        request.user = self.superuser
        self.assertEqual(self.site.airflow_detail(request, "amaris_service_health").status_code, 405)

    @override_settings(
        DEBUG=False,
        AIRFLOW_MONITORING_ENABLED=True,
        AIRFLOW_API_BASE_URL="http://127.0.0.1:8080",
        AIRFLOW_API_TOKEN="test-only",
        AIRFLOW_MONITORED_DAGS=["amaris_service_health"],
    )
    def test_production_refuses_plain_http(self):
        self.assertFalse(is_configured())

    @override_settings(**AIRFLOW_TEST_SETTINGS)
    @patch("amaris_cms.airflow_client.url_request.build_opener")
    def test_no_secrets_in_workflow_response(self, opener):
        class Reply:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self, size):
                return b'{"dag_runs":[{"dag_run_id":"scheduled__2026","state":"success"}]}'

        opener.return_value.open.return_value = Reply()
        result = get_workflow("amaris_service_health")
        self.assertEqual(result["state"], "success")
        self.assertNotIn("test-only-token", repr(result))
        outbound = opener.return_value.open.call_args.args[0]
        self.assertEqual(outbound.get_header("Authorization"), "Bearer test-only-token")
        self.assertEqual(outbound.get_method(), "GET")

    @override_settings(**AIRFLOW_TEST_SETTINGS)
    @patch("amaris_cms.airflow_client._read")
    def test_task_snapshot(self, read):
        read.side_effect = [
            {"dag_runs": [{"dag_run_id": "run-1", "state": "running"}]},
            {"task_instances": [{"task_id": "check_api", "state": "success", "try_number": 1}]},
        ]
        summary, tasks = get_workflow_tasks("amaris_service_health")
        self.assertEqual(summary["state"], "running")
        self.assertEqual(tasks[0]["task_id"], "check_api")

    @override_settings(**AIRFLOW_TEST_SETTINGS, AIRFLOW_API_CA_CERT_FILE="/etc/secrets/airflow-ca.pem")
    @patch("amaris_cms.airflow_client.ssl.create_default_context")
    @patch("amaris_cms.airflow_client.url_request.build_opener")
    def test_private_ca_is_loaded_without_disabling_tls(self, opener, context):
        opener.return_value.open.side_effect = OSError("unreachable")
        with self.assertRaises(AirflowUnavailable):
            get_workflow("amaris_service_health")
        context.assert_called_once_with(cafile="/etc/secrets/airflow-ca.pem")

    @override_settings(**AIRFLOW_TEST_SETTINGS, AIRFLOW_API_CA_CERT_FILE="/missing/airflow-ca.pem")
    @patch("amaris_cms.airflow_client.url_request.build_opener")
    def test_missing_private_ca_fails_closed_before_request(self, opener):
        with self.assertRaises(AirflowUnavailable):
            get_workflow("amaris_service_health")
        opener.assert_not_called()

    @override_settings(**AIRFLOW_TEST_SETTINGS)
    @patch("amaris_cms.airflow_client._read")
    def test_unknown_dag_is_rejected_before_any_call(self, read):
        with self.assertRaises(ValueError):
            get_workflow("internal_payroll")
        read.assert_not_called()

    @override_settings(AIRFLOW_MONITORING_ENABLED=False)
    def test_disabled_status_is_honest(self):
        request = self.factory.get("/admin/airflow/")
        request.user = self.superuser
        response = self.site.airflow_home(request)
        self.assertFalse(response.context_data["airflow_configured"])
        self.assertEqual(response.context_data["workflows"], [])



class AirflowUiUrlTests(SimpleTestCase):
    @override_settings(DEBUG=False, AIRFLOW_UI_URL="https://airflow.example.internal/airflow/")
    def test_https_launch_url_is_normalized(self):
        self.assertEqual(get_airflow_ui_url(), "https://airflow.example.internal/airflow")

    @override_settings(DEBUG=False)
    def test_production_rejects_insecure_and_credentialed_urls(self):
        forbidden = (
            "http://airflow.example.internal",
            "https://user:password@airflow.example.internal",
            "https://airflow.example.internal/?token=secret",
            "https://airflow.example.internal/#access_token",
            "javascript:alert(1)",
            "https://airflow.example.internal\nmalicious",
            "https://airflow.example.internal:invalid/",
            "//airflow.example.internal",
        )
        for url in forbidden:
            with self.subTest(url=url), override_settings(AIRFLOW_UI_URL=url):
                self.assertEqual(get_airflow_ui_url(), "")

    @override_settings(DEBUG=True, AIRFLOW_UI_URL="http://localhost:8080")
    def test_local_development_allows_http(self):
        self.assertEqual(get_airflow_ui_url(), "http://localhost:8080")


class AirflowUiAdminAccessTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.superuser = users.objects.create_superuser(
            username="airflow-admin-test",
            email="airflow-admin@example.invalid",
            password="strong-test-password-only",
        )
        self.staff = users.objects.create_user(
            username="airflow-staff-test",
            email="airflow-staff@example.invalid",
            password="strong-test-password-only",
            is_staff=True,
        )

    @override_settings(
        AIRFLOW_MONITORING_ENABLED=False,
        AIRFLOW_UI_URL="https://airflow.example.internal/airflow",
        AIRFLOW_API_TOKEN="never-render-this-api-token",
    )
    def test_full_ui_link_only_shows_to_django_superuser(self):
        self.client.force_login(self.superuser)
        for url in ("/admin/", "/admin/airflow/", "/admin/monitoring/"):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'href="https://airflow.example.internal/airflow"')
                self.assertContains(response, 'rel="noopener noreferrer"')
                self.assertNotContains(response, "never-render-this-api-token")

        self.client.force_login(self.staff)
        response = self.client.get("/admin/")
        self.assertNotContains(response, "Open full Airflow UI")
        self.assertEqual(self.client.get("/admin/airflow/").status_code, 403)

    @override_settings(DEBUG=False, AIRFLOW_UI_URL="http://insecure.example.com")
    def test_insecure_configuration_does_not_render_link(self):
        self.client.force_login(self.superuser)
        response = self.client.get("/admin/airflow/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'href="http://insecure.example.com"')

    def test_anonymous_cannot_access_airflow_admin(self):
        response = self.client.get("/admin/airflow/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.headers["Location"])
