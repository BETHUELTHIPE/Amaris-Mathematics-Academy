from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse

from amaris_cms.airflow_client import AirflowUnavailable, get_workflow, get_workflow_tasks, is_configured
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
        self.superuser = SimpleNamespace(
            is_authenticated=True, is_active=True, is_staff=True, is_superuser=True
        )
        self.staff = SimpleNamespace(
            is_authenticated=True, is_active=True, is_staff=True, is_superuser=False
        )

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
