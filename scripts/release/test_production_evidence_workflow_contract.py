from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "production-evidence.yml"


class ProductionEvidenceWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_pr_path_runs_only_safe_contract_validation(self) -> None:
        self.assertIn("pull_request:", self.source)
        self.assertIn("workflow_dispatch:", self.source)
        self.assertNotIn("\n  push:", self.source)
        self.assertIn("contract-validation:", self.source)
        self.assertIn("github.event_name == 'workflow_dispatch'", self.source)
        self.assertIn("github.ref == 'refs/heads/main'", self.source)
        self.assertIn("inputs.confirmation == 'RUN_STAGING_EVIDENCE'", self.source)

    def test_operational_drills_are_staging_only(self) -> None:
        self.assertIn("name: staging", self.source)
        self.assertNotIn("environment:\n      name: production", self.source)
        self.assertNotIn("deploy-production", self.source)
        self.assertIn('CAPACITY_ALLOW_PRODUCTION: "false"', self.source)
        self.assertIn("backup-restore-drill.sh staging", self.source)

    def test_release_identity_is_immutable(self) -> None:
        self.assertIn(
            "docker.io/bethuelm/amaris-mathematics-academy:${{ github.sha }}",
            self.source,
        )
        self.assertIn("[0-9a-f]{40}", self.source)
        self.assertIn("ROLLBACK_BASELINE_IMAGE", self.source)
        self.assertIn("promote.sh staging", self.source)
        self.assertIn("__amaris_forced_rollback_probe__", self.source)

    def test_capacity_thresholds_cannot_be_weakened_by_dispatch_inputs(self) -> None:
        self.assertIn("performance/k6/capacity.js", self.source)
        self.assertIn("verify_capacity_infrastructure.py", self.source)
        self.assertNotIn("CAPACITY_MAX_FAILURE_RATE", self.source)
        self.assertNotIn("CAPACITY_MAX_5XX_RATE", self.source)
        self.assertNotIn("CAPACITY_P95_MS", self.source)
        self.assertNotIn("CAPACITY_P99_MS", self.source)
        self.assertIn('          - "50000"', self.source)
        self.assertIn("public_http_concurrent_users_tested", self.source)

    def test_payment_and_email_delivery_are_not_falsely_certified(self) -> None:
        self.assertIn("payment_provider_sandbox_verified: false", self.source)
        self.assertIn("authenticated_email_delivery_verified: false", self.source)
        self.assertIn("production_deployment_performed: false", self.source)

    def test_secrets_are_consumed_as_environment_values_not_printed(self) -> None:
        self.assertIn("secrets.STAGING_BACKUP_TOKEN", self.source)
        self.assertIn("secrets.STAGING_DEPLOY_TOKEN", self.source)
        self.assertIn("secrets.STAGING_CAPACITY_EVIDENCE_TOKEN", self.source)
        self.assertNotIn('echo "${{ secrets.', self.source)
        self.assertNotIn("set -x", self.source)

    def test_evidence_is_retained_without_claiming_unexecuted_work(self) -> None:
        self.assertIn("actions/upload-artifact@v4", self.source)
        self.assertIn("backup_restore_verified: true", self.source)
        self.assertIn("rollback_verified: true", self.source)
        self.assertIn("email_dns_verified: true", self.source)
        self.assertIn("fifty_thousand_users_verified: false", self.source)


if __name__ == "__main__":
    unittest.main()
