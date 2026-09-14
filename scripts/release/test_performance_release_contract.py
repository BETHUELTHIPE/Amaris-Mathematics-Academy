from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LOAD_WORKFLOW = ROOT / ".github" / "workflows" / "load-tests.yml"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "quality-release.yml"
CAPACITY_WORKFLOW = ROOT / ".github" / "workflows" / "production-evidence.yml"
CAPACITY_SCRIPT = ROOT / "performance" / "k6" / "capacity.js"
INFRASTRUCTURE_GATE = ROOT / "scripts" / "release" / "verify_capacity_infrastructure.py"


class PerformanceReleaseContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.load_workflow = LOAD_WORKFLOW.read_text(encoding="utf-8")
        cls.release_workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        cls.capacity_workflow = CAPACITY_WORKFLOW.read_text(encoding="utf-8")
        cls.capacity_script = CAPACITY_SCRIPT.read_text(encoding="utf-8")
        cls.infrastructure_gate = INFRASTRUCTURE_GATE.read_text(encoding="utf-8")

    def test_all_existing_amaris_load_profiles_remain_selectable(self) -> None:
        self.assertIn(
            "options: [smoke, normal, peak, spike, degraded]",
            self.load_workflow,
        )
        self.assertIn("load_tests/run.sh", self.load_workflow)
        self.assertIn("if: always()", self.load_workflow)

    def test_release_performance_failure_is_mandatory(self) -> None:
        start = self.release_workflow.index(
            "- name: PERFORMANCE SMOKE - short production-threshold test"
        )
        end = self.release_workflow.index(
            "- name: OBSERVABILITY CHECK", start
        )
        performance_block = self.release_workflow[start:end]
        self.assertIn("k6 run performance/k6/staging-smoke.js", performance_block)
        self.assertNotIn("continue-on-error", performance_block)
        self.assertNotIn("|| true", performance_block)

    def test_capacity_execution_is_not_part_of_normal_pr_load_workflow(self) -> None:
        self.assertNotIn("performance/k6/capacity.js", self.load_workflow)
        self.assertIn("workflow_dispatch:", self.capacity_workflow)
        self.assertIn("github.ref == 'refs/heads/main'", self.capacity_workflow)
        self.assertIn("inputs.confirmation == 'RUN_STAGING_EVIDENCE'", self.capacity_workflow)

    def test_capacity_http_metrics_are_reported(self) -> None:
        for metric in (
            "rps",
            "p50_ms",
            "p90_ms",
            "p95_ms",
            "p99_ms",
            "failure_percent",
            "http_5xx_percent",
        ):
            with self.subTest(metric=metric):
                self.assertIn(metric, self.capacity_script)

    def test_capacity_infrastructure_components_are_required(self) -> None:
        for metric in (
            "cpu_peak_percent",
            "ram_peak_percent",
            "postgresql_pool_peak_percent",
            "redis_memory_peak_percent",
            "gunicorn_worker_utilization_peak_percent",
            "celery_worker_utilization_peak_percent",
            "celery_queue_backlog_peak",
        ):
            with self.subTest(metric=metric):
                self.assertIn(metric, self.infrastructure_gate)

    def test_fifty_thousand_claim_remains_evidence_gated(self) -> None:
        self.assertIn("50000", self.capacity_script)
        self.assertIn(
            "A 50,000-user claim requires an actual successful 50,000-user run.",
            self.capacity_script,
        )
        self.assertIn("fifty_thousand_users_verified: false", self.capacity_workflow)


if __name__ == "__main__":
    unittest.main()
