"""Offline security regression tests for the production-only approval gate."""

import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).with_name("verify_manual_production_approval.py")
spec = importlib.util.spec_from_file_location("release_gate", MODULE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def approved_settings():
    return {
        "GITHUB_REPOSITORY": gate.REPO,
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_SHA": "a" * 40,
        "PRODUCTION_APPROVED_SHA": "a" * 40,
        "PRODUCTION_ROLLBACK_SHA": "b" * 40,
        "PRODUCTION_APPROVAL_INPUT": "AMARIS-PROD-RELEASE-20261026-001",
        "PRODUCTION_APPROVAL_REFERENCE": "AMARIS-PROD-RELEASE-20261026-001",
        "PRODUCTION_STAGING_RUN_ID": "10001",
        "PRODUCTION_BACKUP_RUN_ID": "10002",
    }


def run_evidence(run_id):
    path = "staging-acceptance.yml" if run_id == 10001 else "genuine-production-public-backup.yml"
    return {
        "id": run_id,
        "status": "completed",
        "conclusion": "success",
        "head_sha": "a" * 40,
        "repository": {"full_name": gate.REPO},
        "event": "workflow_dispatch",
        "path": gate.REPO + "/.github/workflows/" + path + "@refs/heads/main",
    }


class ManualProductionApprovalTests(unittest.TestCase):
    def verify_blocked(self, override=None, alteration=None):
        settings = approved_settings()
        settings.update(override or {})

        def read_run(run_id):
            record = run_evidence(run_id)
            if alteration and run_id == alteration[0]:
                record[alteration[1]] = alteration[2]
            return record

        with self.assertRaises(gate.ReleaseBlocked):
            gate.validate_release(settings, read_run)

    def test_accept_exact_human_approved_sha_with_verified_staging_and_backup(self):
        evidence = gate.validate_release(approved_settings(), run_evidence)
        self.assertEqual(evidence["approved_sha"], "a" * 40)
        self.assertEqual(evidence["rollback_sha"], "b" * 40)

    def test_staging_push_never_implies_approval(self):
        self.verify_blocked({"GITHUB_EVENT_NAME": "push"})

    def test_production_branch_wrong_target_is_denied(self):
        self.verify_blocked({"GITHUB_REF": "refs/heads/production-release-20260923"})

    def test_unauthorized_repository_is_denied(self):
        self.verify_blocked({"GITHUB_REPOSITORY": "attacker/other"})

    def test_missing_or_stale_approved_sha_is_denied(self):
        self.verify_blocked({"PRODUCTION_APPROVED_SHA": ""})
        self.verify_blocked({"PRODUCTION_APPROVED_SHA": "c" * 40})

    def test_owner_approval_reference_must_match(self):
        self.verify_blocked({"PRODUCTION_APPROVAL_INPUT": "WRONG-APPROVAL-REFERENCE"})
        self.verify_blocked({"PRODUCTION_APPROVAL_REFERENCE": ""})

    def test_rollback_commit_cannot_equal_release_commit(self):
        self.verify_blocked({"PRODUCTION_ROLLBACK_SHA": "a" * 40})
        self.verify_blocked({"PRODUCTION_ROLLBACK_SHA": ""})

    def test_staging_and_backup_must_be_distinct(self):
        self.verify_blocked({"PRODUCTION_BACKUP_RUN_ID": "10001"})

    def test_missing_staging_or_backup_run_is_denied(self):
        self.verify_blocked({"PRODUCTION_STAGING_RUN_ID": ""})
        self.verify_blocked({"PRODUCTION_BACKUP_RUN_ID": "abc"})

    def test_evidence_must_be_successful_exact_commit(self):
        self.verify_blocked(alteration=(10001, "conclusion", "failure"))
        self.verify_blocked(alteration=(10002, "head_sha", "c" * 40))
        self.verify_blocked(alteration=(10001, "status", "in_progress"))
        self.verify_blocked(alteration=(10002, "repository", {"full_name": "other/repo"}))

    def test_backup_must_be_explicit_and_from_correct_workflow(self):
        self.verify_blocked(alteration=(10002, "event", "push"))
        self.verify_blocked(alteration=(10002, "path", ".github/workflows/unrelated.yml"))

    def test_staging_must_be_verified_correct_workflow(self):
        self.verify_blocked(alteration=(10001, "path", ".github/workflows/unrelated.yml"))


if __name__ == "__main__":
    unittest.main()
