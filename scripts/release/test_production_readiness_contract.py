from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
READINESS = ROOT / ".github" / "workflows" / "production-readiness.yml"
SECURITY = ROOT / ".github" / "workflows" / "production-security.yml"
POST_DEPLOY = ROOT / "scripts" / "release" / "post-deploy-smoke.sh"
EDGE = ROOT / "scripts" / "release" / "verify-edge-security.sh"
PROVIDER = ROOT / "scripts" / "release" / "provider-readiness.sh"
RESTORE = ROOT / "scripts" / "release" / "backup-restore-drill.sh"
ROLLBACK = ROOT / "scripts" / "release" / "rollback-drill.sh"


class ProductionReadinessContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.readiness = READINESS.read_text(encoding="utf-8")
        cls.security = SECURITY.read_text(encoding="utf-8")
        cls.post_deploy = POST_DEPLOY.read_text(encoding="utf-8")
        cls.edge = EDGE.read_text(encoding="utf-8")
        cls.provider = PROVIDER.read_text(encoding="utf-8")
        cls.restore = RESTORE.read_text(encoding="utf-8")
        cls.rollback = ROLLBACK.read_text(encoding="utf-8")

    def test_readiness_is_manual_main_only_and_staging_scoped(self) -> None:
        self.assertIn("workflow_dispatch:", self.readiness)
        self.assertNotIn("pull_request:", self.readiness)
        self.assertIn("github.ref == 'refs/heads/main'", self.readiness)
        self.assertIn("name: staging", self.readiness)
        self.assertNotIn("name: production", self.readiness)

    def test_readiness_requires_immutable_release_identity(self) -> None:
        for token in ("candidate_sha", "candidate_image", "previous_image"):
            self.assertIn(token, self.readiness)
        self.assertIn("40-character Git SHA", self.readiness)
        self.assertIn(":latest", self.readiness)
        self.assertIn("Candidate and previous images must be different", self.readiness)

    def test_all_operational_evidence_gates_are_mandatory(self) -> None:
        required_commands = (
            "scripts/release/promote.sh staging",
            "scripts/release/post-deploy-smoke.sh",
            "scripts/release/verify-edge-security.sh",
            "scripts/release/provider-readiness.sh staging",
            "scripts/release/backup-restore-drill.sh staging",
            "./load_tests/run.sh",
            "scripts/release/rollback-drill.sh staging",
        )
        for command in required_commands:
            with self.subTest(command=command):
                self.assertIn(command, self.readiness)
        evidence_block = self.readiness.split("steps:", 1)[1]
        self.assertNotIn("continue-on-error", evidence_block)
        self.assertNotIn("|| true", evidence_block)

    def test_readiness_preserves_evidence(self) -> None:
        self.assertIn("actions/upload-artifact@v4", self.readiness)
        self.assertIn("production-readiness-evidence-", self.readiness)
        self.assertIn("retention-days: 90", self.readiness)
        self.assertIn("candidate_git_sha=", self.readiness)
        self.assertIn("candidate_image=", self.readiness)

    def test_smoke_checks_cover_safe_release_surfaces(self) -> None:
        for route in ("/login", "/courses", "/health/", "/health/ready/"):
            with self.subTest(route=route):
                self.assertIn(route, self.post_deploy)
        self.assertIn("/_next/static/", self.post_deploy)
        self.assertIn("requires HTTPS outside localhost", self.post_deploy)

    def test_edge_security_is_fail_closed(self) -> None:
        for header in (
            "Content-Security-Policy",
            "X-Content-Type-Options",
            "Referrer-Policy",
            "Permissions-Policy",
            "Strict-Transport-Security",
            "Cache-Control",
        ):
            with self.subTest(header=header):
                self.assertIn(header, self.edge)
        self.assertIn("private|no-store", self.edge)

    def test_provider_evidence_can_never_create_real_charges(self) -> None:
        self.assertIn("allow_real_charges:false", self.provider)
        self.assertIn("synthetic_only:true", self.provider)
        self.assertIn(".real_charge_created == false", self.provider)
        for evidence in (
            "payfast_sandbox",
            "payment_signature_validation",
            "payment_idempotency",
            "email_delivery",
            "otp_verification",
            "password_reset",
        ):
            with self.subTest(evidence=evidence):
                self.assertIn(f'.{evidence} == "passed"', self.provider)

    def test_restore_drill_requires_integrity_and_application_smoke(self) -> None:
        self.assertIn('.integrity_check == "passed"', self.restore)
        self.assertIn('.application_smoke_check == "passed"', self.restore)
        self.assertIn("backup_id", self.restore)
        self.assertIn("restore_id", self.restore)

    def test_rollback_uses_immutable_distinct_images_and_restores_candidate(self) -> None:
        self.assertIn(":latest", self.rollback)
        self.assertIn("previous_image", self.rollback)
        self.assertIn("candidate_image", self.rollback)
        self.assertIn('deploy-webhook.sh rollback "$environment_name" "$previous_image"', self.rollback)
        self.assertIn('deploy-webhook.sh deploy "$environment_name" "$candidate_image"', self.rollback)
        self.assertGreaterEqual(self.rollback.count("verify-health.sh"), 2)

    def test_security_pipeline_masks_generated_secret(self) -> None:
        self.assertIn("::add-mask::$secret", self.security)
        self.assertIn("DJANGO_SECRET_KEY=%s", self.security)

    def test_security_thresholds_are_not_weakened(self) -> None:
        self.assertIn("npm audit --audit-level=high", self.security)
        self.assertIn("severity: HIGH,CRITICAL", self.security)
        self.assertIn('ignore-unfixed: false', self.security)
        self.assertIn('exit-code: "1"', self.security)
        self.assertIn("gitleaks/gitleaks-action@v2", self.security)


if __name__ == "__main__":
    unittest.main()
