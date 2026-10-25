"""Source-contract checks for fail-closed staging and production promotion."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "quality-release.yml"
BLUEPRINT = ROOT / "render.yaml"


class StagingDatabaseGateContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.blueprint = BLUEPRINT.read_text(encoding="utf-8")

    def test_database_gate_precedes_critical_student_workflows(self):
        staging = self.workflow.split("  deploy-staging:", 1)[1]
        self.assertLess(
            staging.index("DATABASE GATE - PostgreSQL, migrations, and Redis"),
            staging.index("Verify real staging checkout and resume journey"),
        )
        self.assertIn("pending_migrations", staging)
        self.assertIn("ACCEPTANCE", staging)
        self.assertIn("/health/dependencies/", staging)

    def test_staging_must_match_exact_image_revision(self):
        staging = self.workflow.split("  deploy-staging:", 1)[1]
        self.assertIn('deployed_sha" = "${GITHUB_SHA}', staging)
        self.assertIn("git push origin", staging)

    def test_approval_requires_main_and_explicit_confirmation(self):
        production = self.workflow.split("  deploy-production:", 1)[1]
        self.assertIn("github.ref == 'refs/heads/main'", production)
        self.assertIn("inputs.production_approval == 'APPROVE_PRODUCTION'", production)
        self.assertIn("needs: [publish-image, deploy-staging]", production)

    def test_render_predeploy_is_fail_closed(self):
        self.assertIn(
            "preDeployCommand: python manage.py safe_migrate",
            self.blueprint,
        )
        self.assertNotIn("preDeployCommand: python manage.py migrate --noinput", self.blueprint)


if __name__ == "__main__":
    unittest.main()
