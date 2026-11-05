"""Isolated client/command contracts, not live Airflow execution evidence."""

from datetime import UTC, datetime, timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from amaris_cms.airflow_client import AirflowUnavailable, check_runtime, get_airflow_health, get_workflow, is_configured

from .test_airflow_admin import AIRFLOW_TEST_SETTINGS

NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)


def health():
    return {name: {"status": "healthy"} for name in ("metadatabase", "scheduler", "dag_processor")}


def latest(**changes):
    return {
        "dag_runs": [
            {
                "dag_run_id": "scheduled__synthetic",
                "state": "success",
                "run_type": "scheduled",
                "end_date": (NOW - timedelta(minutes=2)).isoformat(),
                **changes,
            }
        ]
    }


@override_settings(**AIRFLOW_TEST_SETTINGS)
class AirflowReadinessTests(SimpleTestCase):
    @patch("amaris_cms.airflow_client._read")
    def test_runtime_requires_health_unpaused_dag_and_fresh_scheduled_success(self, read):
        read.side_effect = [health(), {"dag_id": "amaris_service_health", "is_paused": False}, latest()]
        with patch("amaris_cms.airflow_client.timezone.now", return_value=NOW):
            result = check_runtime("amaris_service_health")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(read.call_args_list[0].args, ("/api/v2/monitor/health",))
        self.assertEqual(read.call_args_list[1].args, ("/api/v2/dags/amaris_service_health",))
        self.assertEqual(read.call_count, 3)
        self.assertNotIn("test-only-token", str(result))

    @patch("amaris_cms.airflow_client._read")
    def test_http_success_with_unhealthy_missing_or_malformed_component_does_not_pass(self, read):
        for status in ("unhealthy", "unknown", None, {"unexpected": "shape"}):
            with self.subTest(status=status):
                payload = health()
                payload["scheduler"] = {"status": status}
                read.return_value = payload
                self.assertFalse(get_airflow_health()["healthy"])
                with self.assertRaises(AirflowUnavailable):
                    check_runtime("amaris_service_health")
        read.return_value = {}
        self.assertFalse(get_airflow_health()["healthy"])

    @patch("amaris_cms.airflow_client._read")
    def test_paused_wrong_or_unknown_dag_is_not_ready(self, read):
        for metadata in (
            {"dag_id": "amaris_service_health", "is_paused": True},
            {"dag_id": "another_workflow", "is_paused": False},
            {"dag_id": "amaris_service_health"},
        ):
            with self.subTest(metadata=metadata):
                read.side_effect = [health(), metadata]
                with self.assertRaises(AirflowUnavailable):
                    check_runtime("amaris_service_health")

    @patch("amaris_cms.airflow_client._read")
    def test_stale_future_naive_failed_or_manual_runs_do_not_pass(self, read):
        for changes in (
            {"end_date": (NOW - timedelta(hours=2)).isoformat()},
            {"end_date": (NOW + timedelta(hours=1)).isoformat()},
            {"end_date": "2026-11-05T12:00:00"},
            {"end_date": "invalid"},
            {"end_date": None},
            {"state": "failed"},
            {"run_type": "manual"},
        ):
            with self.subTest(changes=changes):
                read.side_effect = [
                    health(),
                    {"dag_id": "amaris_service_health", "is_paused": False},
                    latest(**changes),
                ]
                with patch("amaris_cms.airflow_client.timezone.now", return_value=NOW):
                    with self.assertRaises(AirflowUnavailable):
                        check_runtime("amaris_service_health")

    @patch("amaris_cms.airflow_client._read")
    def test_unallowlisted_workflow_or_invalid_freshness_never_reaches_api(self, read):
        with self.assertRaises(ValueError):
            check_runtime("internal_financial_workflow")
        for age in (0, -1, 1441):
            with self.assertRaises(ValueError):
                check_runtime("amaris_service_health", max_run_age_minutes=age)
        read.assert_not_called()

    @override_settings(AIRFLOW_MONITORING_ENABLED=False)
    @patch("amaris_cms.airflow_client.url_request.build_opener")
    def test_disabled_configuration_never_connects(self, opener):
        with self.assertRaises(AirflowUnavailable):
            check_runtime("amaris_service_health")
        opener.assert_not_called()

    def test_bad_endpoint_settings_fail_closed_instead_of_crashing_admin(self):
        for url in (
            "https://private-airflow:bad",
            "https://private-airflow:0",
            "https://[malformed",
            "https://private-airflow/api/v2",
            "https://user:password@private-airflow",
            "https://private-airflow\n",
            "https://private-airflow/?token=private",
            "https://private-airflow\\other-host",
        ):
            with self.subTest(url=url), override_settings(AIRFLOW_API_BASE_URL=url):
                self.assertFalse(is_configured())

    @patch("amaris_cms.airflow_client.url_request.build_opener")
    def test_transport_error_does_not_disclose_secret_to_caller(self, opener):
        opener.return_value.open.side_effect = OSError("test-only-token plus private internals")
        with self.assertRaises(AirflowUnavailable) as caught:
            get_workflow("amaris_service_health")
        self.assertNotIn("test-only-token", str(caught.exception))

    @patch("content.management.commands.check_airflow.check_runtime")
    def test_command_reports_pass_only_after_runtime_acceptance(self, check):
        output = StringIO()
        call_command("check_airflow", stdout=output)
        check.assert_called_once_with("amaris_service_health", max_run_age_minutes=30)
        self.assertIn("PASS:", output.getvalue())

    @patch("content.management.commands.check_airflow.check_runtime")
    def test_command_fails_without_printing_tokens_or_raw_errors(self, check):
        check.side_effect = AirflowUnavailable("test-only-token private error")
        with self.assertRaises(CommandError) as caught:
            call_command("check_airflow", stdout=StringIO())
        self.assertIn("NOT VERIFIED", str(caught.exception))
        self.assertNotIn("test-only-token", str(caught.exception))
