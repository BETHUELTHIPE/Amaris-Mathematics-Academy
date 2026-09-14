from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("verify_capacity_infrastructure.py")
SPEC = importlib.util.spec_from_file_location("verify_capacity_infrastructure", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CapacityInfrastructureEvidenceTests(unittest.TestCase):
    def _valid_payload(self) -> dict[str, object]:
        return {
            "environment": "staging",
            "release_sha": "b" * 40,
            "capacity_users": 500,
            "observation_seconds": 420,
            "cpu_peak_percent": 60,
            "ram_peak_percent": 70,
            "postgresql_pool_peak_percent": 65,
            "redis_memory_peak_percent": 50,
            "gunicorn_worker_utilization_peak_percent": 55,
            "celery_worker_utilization_peak_percent": 45,
            "celery_queue_backlog_peak": 20,
            "gunicorn_restarts": 0,
            "postgresql_errors": 0,
            "redis_errors": 0,
            "celery_errors": 0,
        }

    def test_valid_evidence_passes(self) -> None:
        normalized = MODULE.validate(
            self._valid_payload(),
            expected_sha="b" * 40,
            expected_users=500,
            minimum_window_seconds=420,
        )
        self.assertTrue(normalized["infrastructure_thresholds_passed"])
        self.assertEqual(
            normalized["components_measured"],
            ["CPU", "RAM", "PostgreSQL", "Redis", "Gunicorn", "Celery"],
        )

    def test_release_identity_mismatch_fails(self) -> None:
        with self.assertRaises(MODULE.EvidenceError):
            MODULE.validate(
                self._valid_payload(),
                expected_sha="c" * 40,
                expected_users=500,
                minimum_window_seconds=420,
            )

    def test_user_count_mismatch_fails(self) -> None:
        with self.assertRaises(MODULE.EvidenceError):
            MODULE.validate(
                self._valid_payload(),
                expected_sha="b" * 40,
                expected_users=1000,
                minimum_window_seconds=420,
            )

    def test_observation_window_must_cover_test(self) -> None:
        payload = self._valid_payload()
        payload["observation_seconds"] = 419
        with self.assertRaises(MODULE.EvidenceError):
            MODULE.validate(
                payload,
                expected_sha="b" * 40,
                expected_users=500,
                minimum_window_seconds=420,
            )

    def test_thresholds_fail_closed(self) -> None:
        payload = self._valid_payload()
        payload["cpu_peak_percent"] = 85.01
        payload["postgresql_errors"] = 1
        with self.assertRaises(MODULE.EvidenceError) as context:
            MODULE.validate(
                payload,
                expected_sha="b" * 40,
                expected_users=500,
                minimum_window_seconds=420,
            )
        self.assertIn("cpu_peak_percent", str(context.exception))
        self.assertIn("postgresql_errors", str(context.exception))

    def test_each_required_component_metric_is_fail_closed(self) -> None:
        required_metrics = (
            "cpu_peak_percent",
            "ram_peak_percent",
            "postgresql_pool_peak_percent",
            "redis_memory_peak_percent",
            "gunicorn_worker_utilization_peak_percent",
            "celery_worker_utilization_peak_percent",
            "celery_queue_backlog_peak",
            "gunicorn_restarts",
            "postgresql_errors",
            "redis_errors",
            "celery_errors",
        )
        for metric in required_metrics:
            with self.subTest(metric=metric):
                payload = self._valid_payload()
                del payload[metric]
                with self.assertRaises(MODULE.EvidenceError):
                    MODULE.validate(
                        payload,
                        expected_sha="b" * 40,
                        expected_users=500,
                        minimum_window_seconds=420,
                    )

    def test_boolean_metrics_are_rejected(self) -> None:
        payload = self._valid_payload()
        payload["gunicorn_restarts"] = False
        with self.assertRaises(MODULE.EvidenceError):
            MODULE.validate(
                payload,
                expected_sha="b" * 40,
                expected_users=500,
                minimum_window_seconds=420,
            )


if __name__ == "__main__":
    unittest.main()
