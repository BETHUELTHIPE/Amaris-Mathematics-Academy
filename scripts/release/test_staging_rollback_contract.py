"""Regression contract for staging rollback to the last known-good immutable image."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "quality-release.yml"


class StagingRollbackContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = WORKFLOW.read_text(encoding="utf-8")
        cls.staging = source.split("  staging-release-gate:", 1)[1].split(
            "  deploy-production:", 1
        )[0]

    def test_current_release_is_verified_before_staging_deploy(self):
        capture = self.staging.index(
            "STAGING - capture previous immutable release for rollback"
        )
        deploy = self.staging.index("STAGING - deploy exact immutable image")
        self.assertLess(capture, deploy)
        self.assertIn(
            'deploy-webhook.sh current-release staging', self.staging
        )
        self.assertIn("^[0-9a-f]{40}$", self.staging)
        self.assertIn("steps.previous.outputs.image", self.staging)

    def test_rollback_uses_previous_image_not_failed_candidate(self):
        rollback = self.staging.split(
            "- name: Roll back staging if any post-deploy gate fails", 1
        )[1]
        self.assertIn('rollback staging "$previous_image"', rollback)
        self.assertNotIn(
            'rollback staging "${{ needs.publish-image.outputs.image }}"',
            rollback,
        )
        self.assertIn(
            "steps.previous.outcome == 'success'", rollback
        )

    def test_rollback_health_and_identity_must_both_pass(self):
        rollback = self.staging.split(
            "- name: Roll back staging if any post-deploy gate fails", 1
        )[1]
        self.assertIn('set -euo pipefail', rollback)
        self.assertIn(
            'verify-health.sh "$STAGING_HEALTHCHECK_URL"', rollback
        )
        self.assertNotIn(
            'verify-health.sh "$STAGING_HEALTHCHECK_URL" || true',
            rollback,
        )
        self.assertIn('active_image', rollback)
        self.assertIn('active_sha', rollback)
        self.assertIn(
            "Rollback did not restore the previously recorded immutable staging release.",
            rollback,
        )


if __name__ == "__main__":
    unittest.main()
