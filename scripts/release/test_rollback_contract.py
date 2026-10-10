"""Fail-closed deployment and exact previous-version rollback regression tests.

These tests use local fake host actions and never contact Render, Docker Hub,
PayFast, or any production/staging endpoint.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RELEASE_DIR = ROOT / "scripts" / "release"
IMAGE = "docker.io/bethuelm/amaris-mathematics-academy:"
OLD = IMAGE + "a" * 40
NEW = IMAGE + "b" * 40

HOST = """#!/bin/sh
set -eu
case "$1" in
    current-release)
        active=$(cat "$FAKE_STATE")
        if [ "$active" = "invalid" ]; then
            echo '{"status":"ok","image":"latest","git_sha":"unknown"}'
        else
            printf '{"status":"ok","image":"%s","git_sha":"%s"}\\n' "$active" "${active##*:}"
        fi
        ;;
    deploy|rollback)
        echo "$1:$3" >> "$FAKE_EVENTS"
        if [ "$1" = "rollback" ] && [ "${FAIL_ROLLBACK:-}" = "1" ]; then
            exit 1
        fi
        printf '%s' "$3" > "$FAKE_STATE"
        ;;
    *) exit 2 ;;
esac
"""

HEALTH = """#!/bin/sh
set -eu
active=$(cat "$FAKE_STATE")
if [ "$active" = "${FAKE_FAIL_IMAGE:-}" ] || [ "$active" = "${FAKE_FAIL_ROLLBACK_HEALTH:-}" ]; then
    exit 1
fi
exit 0
"""


@unittest.skipUnless(shutil.which("jq"), "jq is required for release JSON validation")
class ImmutableRollbackContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="amaris-rollback-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        release = self.root / "scripts" / "release"
        release.mkdir(parents=True)
        shutil.copyfile(RELEASE_DIR / "promote.sh", release / "promote.sh")
        for name, data in (("deploy-webhook.sh", HOST), ("verify-health.sh", HEALTH)):
            target = release / name
            target.write_text(data, encoding="utf-8")
            target.chmod(0o755)
        self.state = self.root / "active-image"
        self.events = self.root / "events"
        self.state.write_text(OLD, encoding="utf-8")
        self.events.write_text("", encoding="utf-8")

    def run_promotion(self, image=NEW, **extra):
        environment = os.environ.copy()
        environment.update({
            "HEALTHCHECK_URL": "https://staging.example.test/health/",
            "GITHUB_SHA": NEW.split(":")[-1],
            "FAKE_STATE": str(self.state),
            "FAKE_EVENTS": str(self.events),
            **extra,
        })
        return subprocess.run(
            ["sh", "scripts/release/promote.sh", "staging", image],
            cwd=self.root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    def event_log(self):
        return self.events.read_text(encoding="utf-8").splitlines()

    def test_failed_candidate_restores_exact_previous_image_and_health(self):
        result = self.run_promotion(FAKE_FAIL_IMAGE=NEW)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.state.read_text(encoding="utf-8"), OLD)
        self.assertEqual(self.event_log(), [f"deploy:{NEW}", f"rollback:{OLD}"])
        self.assertIn("Rollback verified", result.stderr)

    def test_healthy_candidate_promotes_without_rollback(self):
        result = self.run_promotion()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.state.read_text(encoding="utf-8"), NEW)
        self.assertEqual(self.event_log(), [f"deploy:{NEW}"])

    def test_ambiguous_latest_rejected_before_deployment(self):
        result = self.run_promotion(image=IMAGE + "latest")
        self.assertEqual(result.returncode, 64)
        self.assertEqual(self.event_log(), [])
        self.assertEqual(self.state.read_text(encoding="utf-8"), OLD)

    def test_release_sha_mismatch_rejected_before_deployment(self):
        result = self.run_promotion(GITHUB_SHA="c" * 40)
        self.assertEqual(result.returncode, 64)
        self.assertEqual(self.event_log(), [])

    def test_untrusted_previous_version_refused_before_deployment(self):
        self.state.write_text("invalid", encoding="utf-8")
        result = self.run_promotion()
        self.assertEqual(result.returncode, 65)
        self.assertEqual(self.event_log(), [])

    def test_rollback_execution_failure_is_not_claimed_as_recovery(self):
        result = self.run_promotion(FAKE_FAIL_IMAGE=NEW, FAIL_ROLLBACK="1")
        self.assertEqual(result.returncode, 71, result.stderr)
        self.assertEqual(self.state.read_text(encoding="utf-8"), NEW)
        self.assertNotIn("Rollback verified", result.stderr)

    def test_unhealthy_restored_version_fails_closed(self):
        result = self.run_promotion(
            FAKE_FAIL_IMAGE=NEW,
            FAKE_FAIL_ROLLBACK_HEALTH=OLD,
        )
        self.assertEqual(result.returncode, 72, result.stderr)
        self.assertEqual(self.state.read_text(encoding="utf-8"), OLD)
        self.assertNotIn("Rollback verified", result.stderr)

    def test_idempotent_healthy_release_never_mutates(self):
        self.state.write_text(NEW, encoding="utf-8")
        result = self.run_promotion()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.event_log(), [])


if __name__ == "__main__":
    unittest.main()
