"""Offline acceptance tests: no live Airflow API or paid resources required."""

import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("amaris_live_readiness", HERE / "render/live_readiness.py")
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


class Reply:
    status = 200

    def __init__(self, body):
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, amount):
        return self.body[:amount]


class LiveReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        ca = Path(self.temp.name) / "ca.pem"
        ca.write_text("test-only-ca")
        self.env = {
            "AIRFLOW_API_BASE_URL": "https://airflow.internal:8443",
            "AIRFLOW_API_TOKEN": "test-only-token",
            "AIRFLOW_API_CA_CERT_FILE": str(ca),
            "AIRFLOW_MONITORED_DAG": "amaris_service_health",
            "AIRFLOW_MAX_RUN_AGE_MINUTES": "35",
        }
        self.responses = [
            {
                "metadatabase": {"status": "healthy"},
                "scheduler": {"status": "healthy"},
                "dag_processor": {"status": "healthy"},
            },
            {"dag_id": "amaris_service_health", "is_paused": False},
            {
                "dag_runs": [
                    {
                        "state": "success",
                        "end_date": (NOW - timedelta(minutes=10)).isoformat(),
                    }
                ]
            },
        ]

    def evaluate(self):
        with (
            patch.object(PROBE.ssl, "create_default_context") as context,
            patch.object(PROBE.request, "build_opener") as factory,
        ):
            client = factory.return_value
            client.open.side_effect = [Reply(x) for x in self.responses]
            result = PROBE.check(self.env, now=NOW)
            self.assertEqual(context.call_args.kwargs["cafile"], self.env["AIRFLOW_API_CA_CERT_FILE"])
            return result, client

    def test_verified_typed_read_only_requests_and_fresh_success(self):
        result, client = self.evaluate()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(client.open.call_count, 3)
        for call in client.open.call_args_list:
            outgoing = call.args[0]
            self.assertEqual(outgoing.get_method(), "GET")
            self.assertEqual(outgoing.get_header("Authorization"), "Bearer test-only-token")
            self.assertTrue(outgoing.full_url.startswith("https://airflow.internal:8443/api/v2/"))

    def test_fails_on_unhealthy_scheduler(self):
        self.responses[0]["scheduler"]["status"] = "unhealthy"
        with self.assertRaises(PROBE.ReadinessError):
            self.evaluate()

    def test_fails_on_missing_dag_processor_heartbeat(self):
        self.responses[0].pop("dag_processor")
        with self.assertRaises(PROBE.ReadinessError):
            self.evaluate()

    def test_fails_on_paused_dag(self):
        self.responses[1]["is_paused"] = True
        with self.assertRaises(PROBE.ReadinessError):
            self.evaluate()

    def test_fails_on_stale_successful_run(self):
        self.responses[2]["dag_runs"][0]["end_date"] = (NOW - timedelta(minutes=36)).isoformat()
        with self.assertRaises(PROBE.ReadinessError):
            self.evaluate()

    def test_fails_on_latest_failed_run_even_if_an_older_run_succeeded(self):
        self.responses[2]["dag_runs"][0]["state"] = "failed"
        with self.assertRaises(PROBE.ReadinessError):
            self.evaluate()

    def test_fails_on_future_run(self):
        self.responses[2]["dag_runs"][0]["end_date"] = (NOW + timedelta(minutes=6)).isoformat()
        with self.assertRaises(PROBE.ReadinessError):
            self.evaluate()

    def test_fails_on_malformed_health_response(self):
        self.responses[0]["scheduler"] = None
        with self.assertRaises(PROBE.ReadinessError):
            self.evaluate()

    def test_fails_on_malformed_dag_run(self):
        self.responses[2]["dag_runs"] = [None]
        with self.assertRaises(PROBE.ReadinessError):
            self.evaluate()

    def test_rejects_insecure_urls_embedded_credentials_and_missing_secrets(self):
        for url in ("http://airflow.internal", "https://user:pass@airflow.internal", "https://airflow.internal/path"):
            with self.subTest(url=url), self.assertRaises(PROBE.ReadinessError):
                PROBE.check(dict(self.env, AIRFLOW_API_BASE_URL=url), now=NOW)
        with self.assertRaises(PROBE.ReadinessError):
            PROBE.check(dict(self.env, AIRFLOW_API_TOKEN=""), now=NOW)

    def test_redirect_handler_does_not_forward_bearer_token(self):
        self.assertIsNone(PROBE.NoRedirect().redirect_request(None, None, 302, None, None, "https://evil.test"))

    def test_does_not_report_pass_when_tls_api_unreachable(self):
        with (
            patch.object(PROBE.ssl, "create_default_context"),
            patch.object(PROBE.request, "build_opener") as factory,
        ):
            factory.return_value.open.side_effect = OSError("private network unavailable")
            with self.assertRaises(PROBE.ReadinessError) as caught:
                PROBE.check(self.env, now=NOW)
            self.assertNotIn("test-only-token", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
