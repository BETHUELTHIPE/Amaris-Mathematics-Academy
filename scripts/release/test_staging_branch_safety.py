"""Network-free release regression: staging promotion may never rewrite history."""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, check=True, text=True, capture_output=True
    )
    return result.stdout.strip()


def staging_step() -> str:
    workflow = (ROOT / ".github/workflows/quality-release.yml").read_text(
        encoding="utf-8"
    )
    label = "      - name: Advance Render staging branch without rewriting history"
    assert workflow.count(label) == 1, "safe staging promotion step is missing"
    section = workflow.split(label, 1)[1].split("\n      - name:", 1)[0]
    assert "        run: |\n" in section, "staging promotion script is missing"
    lines = section.split("        run: |\n", 1)[1].splitlines()
    return "\n".join(line[10:] for line in lines if line.startswith("          "))


class StagingPromotionSafetyTests(unittest.TestCase):
    def test_script_refuses_force_pushes(self):
        script = staging_step()
        self.assertIn("git merge-base --is-ancestor origin/staging", script)
        self.assertIn('git push origin "${GITHUB_SHA}:refs/heads/staging"', script)
        self.assertNotIn("--force", script)
        self.assertNotIn("push -f", script)

    def test_fast_forward_allowed_and_divergent_history_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            remote, checkout = root / "remote.git", root / "checkout"
            git(root, "init", "--bare", str(remote))
            git(root, "init", "-b", "staging", str(checkout))
            git(checkout, "config", "user.email", "release-test@example.invalid")
            git(checkout, "config", "user.name", "Release Test")
            git(checkout, "remote", "add", "origin", str(remote))
            git(checkout, "commit", "--allow-empty", "-m", "Version N")
            git(checkout, "push", "origin", "HEAD:refs/heads/staging")

            git(checkout, "commit", "--allow-empty", "-m", "Version N+1")
            candidate = git(checkout, "rev-parse", "HEAD")
            env = dict(os.environ, GITHUB_SHA=candidate)
            accepted = subprocess.run(
                ["bash", "-c", staging_step()],
                cwd=checkout, env=env, capture_output=True, text=True, check=False
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertEqual(
                git(remote, "rev-parse", "refs/heads/staging"), candidate
            )

            # Candidate branches off N, not N+1: it must not overwrite staging.
            git(checkout, "checkout", "-b", "divergent", "HEAD~1")
            git(checkout, "commit", "--allow-empty", "-m", "Divergent release")
            env["GITHUB_SHA"] = git(checkout, "rev-parse", "HEAD")
            rejected = subprocess.run(
                ["bash", "-c", staging_step()],
                cwd=checkout, env=env, capture_output=True, text=True, check=False
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(
                git(remote, "rev-parse", "refs/heads/staging"), candidate
            )


if __name__ == "__main__":
    unittest.main()
