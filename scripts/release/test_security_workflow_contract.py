from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "security.yml"


class SecurityWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_security_workflow_uses_current_node24_action_majors(self) -> None:
        self.assertIn("actions/checkout@v7", self.source)
        self.assertIn("actions/setup-python@v7", self.source)
        self.assertIn("actions/setup-node@v7", self.source)

        for legacy_action in (
            "actions/checkout@v4",
            "actions/setup-python@v5",
            "actions/setup-python@v6",
            "actions/setup-node@v4",
            "actions/setup-node@v6",
        ):
            with self.subTest(legacy_action=legacy_action):
                self.assertNotIn(legacy_action, self.source)

    def test_deploy_check_secret_is_ephemeral_and_masked(self) -> None:
        self.assertNotRegex(self.source, r"DJANGO_SECRET_KEY:\s*[\"'][^\n]+")
        self.assertIn('secret="$(openssl rand -hex 64)"', self.source)
        self.assertIn('echo "::add-mask::$secret"', self.source)
        self.assertIn(
            "printf 'DJANGO_SECRET_KEY=%s\\n' \"$secret\" >> \"$GITHUB_ENV\"",
            self.source,
        )

    def test_workflow_never_enables_shell_trace_or_echoes_secrets(self) -> None:
        self.assertNotIn("set -x", self.source)
        self.assertNotIn('echo "${{ secrets.', self.source)


if __name__ == "__main__":
    unittest.main()
