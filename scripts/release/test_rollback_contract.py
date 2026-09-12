from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMOTE_SCRIPT = REPO_ROOT / "scripts" / "release" / "promote.sh"
IMAGE_PREFIX = "docker.io/bethuelm/amaris-mathematics-academy:"


class RollbackContractTests(unittest.TestCase):
    def _sandbox(self, directory: Path, version_n_sha: str) -> tuple[Path, dict[str, str]]:
        release_dir = directory / "scripts" / "release"
        release_dir.mkdir(parents=True)
        promote = release_dir / "promote.sh"
        shutil.copy2(PROMOTE_SCRIPT, promote)
        promote.chmod(0o700)

        deploy_client = release_dir / "deploy-webhook.sh"
        deploy_client.write_text(
            """#!/bin/sh
set -eu
case "$1" in
    current-release)
        printf '{"status":"succeeded","image":"%s","release_sha":"%s"}\n' "$VERSION_N_IMAGE" "$VERSION_N_SHA"
        ;;
    deploy|rollback)
        printf '%s|%s|%s\n' "$1" "$2" "$3" >> "$ACTION_LOG"
        ;;
    *)
        exit 2
        ;;
esac
""",
            encoding="utf-8",
        )
        deploy_client.chmod(0o700)

        health_client = release_dir / "verify-health.sh"
        health_client.write_text(
            """#!/bin/sh
set -eu
count=0
if [ -f "$HEALTH_COUNT_FILE" ]; then
    count=$(cat "$HEALTH_COUNT_FILE")
fi
count=$((count + 1))
printf '%s\n' "$count" > "$HEALTH_COUNT_FILE"
if [ "$count" -eq 1 ]; then
    exit 1
fi
exit 0
""",
            encoding="utf-8",
        )
        health_client.chmod(0o700)

        version_n_image = f"{IMAGE_PREFIX}{version_n_sha}"
        env = os.environ.copy()
        env.update(
            {
                "HEALTHCHECK_URL": "https://production.example/health/ready/",
                "VERSION_N_IMAGE": version_n_image,
                "VERSION_N_SHA": version_n_sha,
                "ACTION_LOG": str(directory / "actions.log"),
                "HEALTH_COUNT_FILE": str(directory / "health-count.txt"),
                "DEPLOYMENT_RECORD_FILE": str(directory / "deployment-version.json"),
                "GITHUB_STEP_SUMMARY": str(directory / "step-summary.md"),
            }
        )
        return promote, env

    def test_failed_candidate_restores_version_n_and_health_passes(self):
        version_n_sha = "1" * 40
        version_n_plus_1_sha = "2" * 40
        version_n_image = f"{IMAGE_PREFIX}{version_n_sha}"
        candidate_image = f"{IMAGE_PREFIX}{version_n_plus_1_sha}"

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            promote, env = self._sandbox(directory, version_n_sha)
            result = subprocess.run(
                [str(promote), "production", candidate_image],
                cwd=directory,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 1, result.stderr)
            actions = (directory / "actions.log").read_text(encoding="utf-8").splitlines()
            self.assertEqual(
                actions,
                [
                    f"deploy|production|{candidate_image}",
                    f"rollback|production|{version_n_image}",
                ],
            )
            self.assertEqual((directory / "health-count.txt").read_text().strip(), "2")

            record = json.loads((directory / "deployment-version.json").read_text())
            self.assertEqual(record["status"], "rolled-back")
            self.assertEqual(record["candidate"]["git_sha"], version_n_plus_1_sha)
            self.assertEqual(record["candidate"]["image"], candidate_image)
            self.assertEqual(record["active"]["git_sha"], version_n_sha)
            self.assertEqual(record["active"]["image"], version_n_image)
            self.assertEqual(record["rollback_health"], "passed")

            summary = (directory / "step-summary.md").read_text(encoding="utf-8")
            self.assertIn(version_n_sha, summary)
            self.assertIn(version_n_image, summary)
            self.assertIn(version_n_plus_1_sha, summary)
            self.assertIn(candidate_image, summary)
            self.assertIn("Final status: rolled-back", summary)

    def test_ambiguous_latest_candidate_is_rejected_before_deploy(self):
        version_n_sha = "3" * 40
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            promote, env = self._sandbox(directory, version_n_sha)
            result = subprocess.run(
                [str(promote), "production", f"{IMAGE_PREFIX}latest"],
                cwd=directory,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("latest is not an accepted deployment identity", result.stderr)
            self.assertFalse((directory / "actions.log").exists())


if __name__ == "__main__":
    unittest.main()
