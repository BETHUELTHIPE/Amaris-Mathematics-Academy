from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
QUALITY_WORKFLOW = WORKFLOWS_DIR / "quality-release.yml"

PRODUCTION_SECRET_NAMES = (
    "PRODUCTION_BACKUP_WEBHOOK_URL",
    "PRODUCTION_BACKUP_TOKEN",
    "PRODUCTION_DEPLOY_WEBHOOK_URL",
    "PRODUCTION_DEPLOY_TOKEN",
)


class ProductionEnvironmentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = QUALITY_WORKFLOW.read_text(encoding="utf-8")
        match = re.search(
            r"(?ms)^  deploy-production:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)",
            cls.workflow,
        )
        if not match:
            raise AssertionError("deploy-production job is missing")
        cls.production_job = match.group(0)
        cls.production_job_span = match.span()

    def test_production_uses_named_environment(self):
        self.assertRegex(
            self.production_job,
            r"(?ms)^    environment:\n      name: production$",
        )

    def test_production_requires_explicit_manual_approval(self):
        self.assertIn("production_approval:", self.workflow)
        self.assertIn("- DO_NOT_DEPLOY", self.workflow)
        self.assertIn("- APPROVE_PRODUCTION", self.workflow)
        self.assertIn("default: DO_NOT_DEPLOY", self.workflow)
        self.assertIn("inputs.deploy_production == true", self.production_job)
        self.assertIn(
            "inputs.production_approval == 'APPROVE_PRODUCTION'",
            self.production_job,
        )

    def test_production_deployments_are_serialized(self):
        self.assertRegex(
            self.production_job,
            r"(?ms)^    concurrency:\n      group: production-deployment\n      cancel-in-progress: false$",
        )

    def test_production_secrets_are_referenced_only_by_production_job(self):
        start, end = self.production_job_span
        outside_production_job = self.workflow[:start] + self.workflow[end:]

        for secret_name in PRODUCTION_SECRET_NAMES:
            self.assertIn(secret_name, self.production_job)
            self.assertNotIn(secret_name, outside_production_job)

        for workflow_path in WORKFLOWS_DIR.glob("*.y*ml"):
            if workflow_path == QUALITY_WORKFLOW:
                continue
            content = workflow_path.read_text(encoding="utf-8")
            for secret_name in PRODUCTION_SECRET_NAMES:
                self.assertNotIn(
                    secret_name,
                    content,
                    msg=f"{secret_name} must not be referenced by {workflow_path.name}",
                )

    def test_production_job_has_minimal_repository_permissions(self):
        self.assertRegex(
            self.production_job,
            r"(?ms)^    permissions:\n      contents: read$",
        )


if __name__ == "__main__":
    unittest.main()
