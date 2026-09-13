import copy
import json
import signal
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from production_deploy import IMAGE_REPOSITORY, Adapter, Deployment, identity
from verify_production_approval import validate

N = identity(f"{IMAGE_REPOSITORY}:{'1' * 40}", "1" * 40, "sha256:" + "a" * 64)
CANDIDATE = identity(f"{IMAGE_REPOSITORY}:{'2' * 40}", "2" * 40, "sha256:" + "b" * 64)


class FakeHosting:
    transaction = "123-1"

    def __init__(self, fail=None):
        self.fail = fail
        self.active = N
        self.events = []
        self.journeys = 0

    def call(self, action, release=None, **extra):
        self.events.append(action)
        if action == "deploy":
            self.active = release  # Side effect happens BEFORE a lost response.
        if self.fail == action:
            raise ConnectionError("SECRET-REMOTE-RESPONSE")
        if action == "rollback":
            self.active = release
        response = {
            "status": "completed",
            "transaction_id": self.transaction,
            "release": release,
        }
        if action == "preflight":
            response.update(
                registry_verified=True,
                ready=True,
                rollback_compatible=True,
                watchdog_ready=True,
            )
        elif action == "acquire":
            response.update(previous=self.active, watchdog_armed=True)
        elif action == "status":
            response.update(active=self.active)
        elif action == "backup":
            response.update(verified=True, recovery_id="recovery-123")
        elif action == "migration-plan":
            response.update(backwards_compatible=True, destructive=False)
        elif action == "migrate":
            response.update(pending=0, backwards_compatible=True)
        elif action == "monitor":
            response.update(healthy=True, critical_alerts=0)
        if self.fail == "unsafe-plan" and action == "migration-plan":
            response["destructive"] = True
        if self.fail == "bad-backup" and action == "backup":
            response["verified"] = False
        if self.fail == "wrong-digest" and action == "preflight":
            response["release"] = N
        if self.fail == "wrong-transaction" and action == "backup":
            response["transaction_id"] = "old-transaction"
        if self.fail == "pending-migration" and action == "migrate":
            response["pending"] = 1
        if self.fail == "critical-alert" and action == "monitor":
            response["critical_alerts"] = 1
        return response

    def health(self, release):
        self.events.append("health")
        if self.fail == "health" and release == CANDIDATE:
            raise ValueError("unhealthy")

    def journey(self):
        self.events.append("journey")
        self.journeys += 1
        if self.fail == "journey" and self.journeys == 1:
            raise ValueError("login failed")
        if self.fail == "cancel" and self.journeys == 1:
            raise KeyboardInterrupt()

    def smoke(self, release):
        self.events.append("smoke")
        if self.fail == "smoke" and release == CANDIDATE:
            raise ValueError("static assets failed")
        return [{"name": "public-checks", "status": "passed"}]


class ProductionTransactionTests(unittest.TestCase):
    def deploy(self, host):
        with tempfile.TemporaryDirectory() as directory, patch.object(signal, "signal"):
            path = Path(directory) / "record.json"
            sleeps = []
            transaction = Deployment(host, CANDIDATE, path, sleep=sleeps.append)
            result = transaction.execute()
            record = json.loads(path.read_text())
            self.assertNotIn("SECRET-REMOTE-RESPONSE", path.read_text())
            return result, record, sleeps

    def test_success_has_ordered_backup_migration_checks_and_five_minute_monitor(self):
        host = FakeHosting()
        result, record, sleeps = self.deploy(host)
        self.assertEqual(result, 0)
        self.assertEqual(record["outcome"], "deployed")
        for first, second in [
            ("preflight", "acquire"),
            ("backup", "deploy"),
            ("migration-plan", "deploy"),
            ("deploy", "migrate"),
            ("migrate", "journey"),
            ("migrate", "smoke"),
            ("smoke", "journey"),
            ("journey", "monitor"),
            ("monitor", "commit"),
        ]:
            self.assertLess(host.events.index(first), host.events.index(second))
        self.assertEqual(host.events.count("monitor"), 10)
        self.assertEqual(sum(sleeps), 300)
        self.assertNotIn("rollback", host.events)

    def test_failures_before_mutation_block_without_deploying(self):
        for failure in [
            "preflight",
            "acquire",
            "backup",
            "bad-backup",
            "unsafe-plan",
            "wrong-digest",
            "wrong-transaction",
        ]:
            with self.subTest(failure=failure):
                host = FakeHosting(failure)
                result, record, _ = self.deploy(host)
                self.assertEqual(result, 1)
                self.assertEqual(record["outcome"], "blocked")
                self.assertNotIn("deploy", host.events)
                self.assertNotIn("rollback", host.events)

    def test_all_failures_after_mutation_restore_and_verify_n(self):
        for failure in [
            "deploy",
            "migrate",
            "pending-migration",
            "health",
            "smoke",
            "journey",
            "critical-alert",
            "monitor",
            "commit",
            "cancel",
        ]:
            with self.subTest(failure=failure):
                host = FakeHosting(failure)
                result, record, _ = self.deploy(host)
                self.assertEqual(result, 1)
                self.assertEqual(record["outcome"], "rolled_back")
                self.assertEqual(record["restored"], N)
                self.assertEqual(host.active, N)
                rollback_at = host.events.index("rollback")
                self.assertIn("health", host.events[rollback_at:])
                self.assertIn("smoke", host.events[rollback_at:])
                self.assertIn("journey", host.events[rollback_at:])

    def test_failed_rollback_keeps_lock_and_watchdog(self):
        host = FakeHosting("rollback")
        host.journey = lambda: (_ for _ in ()).throw(ValueError("failed journey"))
        result, record, _ = self.deploy(host)
        self.assertEqual(result, 2)
        self.assertEqual(record["outcome"], "rollback_failed")
        self.assertNotIn("abort", host.events)

    def test_same_release_is_still_verified(self):
        host = FakeHosting()
        host.active = CANDIDATE
        result, _, _ = self.deploy(host)
        self.assertEqual(result, 0)
        self.assertIn("journey", host.events)
        self.assertEqual(host.events.count("monitor"), 10)

    def test_rejects_latest_wrong_sha_repository_and_missing_digest(self):
        for image, sha, digest in [
            (f"{IMAGE_REPOSITORY}:latest", CANDIDATE["git_sha"], CANDIDATE["digest"]),
            (CANDIDATE["image"], N["git_sha"], CANDIDATE["digest"]),
            (
                "attacker/image:" + CANDIDATE["git_sha"],
                CANDIDATE["git_sha"],
                CANDIDATE["digest"],
            ),
            (CANDIDATE["image"], CANDIDATE["git_sha"], ""),
        ]:
            with self.assertRaises(ValueError):
                identity(image, sha, digest)

    def test_browser_does_not_receive_deployment_credentials(self):
        adapter = object.__new__(Adapter)
        adapter.env = {
            "DEPLOY_TOKEN": "secret",
            "BACKUP_TOKEN": "secret",
            "GH_TOKEN": "secret",
            "PRODUCTION_STUDENT_PASSWORD": "synthetic-password",
            "PATH": "/bin",
        }
        with patch("production_deploy.subprocess.run") as run:
            adapter.journey()
        env = run.call_args.kwargs["env"]
        self.assertNotIn("DEPLOY_TOKEN", env)
        self.assertNotIn("BACKUP_TOKEN", env)
        self.assertNotIn("GH_TOKEN", env)
        self.assertIn("PRODUCTION_STUDENT_PASSWORD", env)


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.environment = {
            "name": "production",
            "id": 7,
            "protection_rules": [{"type": "required_reviewers", "reviewers": [{"type": "User"}]}],
            "deployment_branch_policy": {"custom_branch_policies": True},
        }
        self.policies = {"branch_policies": [{"name": "main", "type": "branch"}]}
        self.reviews = [{"state": "approved", "environments": [{"id": 7}]}]
        self.run = {"head_sha": CANDIDATE["git_sha"], "head_branch": "main"}

    def check(self):
        return validate(
            self.environment,
            self.policies,
            self.reviews,
            self.run,
            CANDIDATE["git_sha"],
        )

    def test_native_approval_passes(self):
        self.assertTrue(self.check())

    def test_missing_rules_or_approval_or_wrong_run_block(self):
        for key, value in [
            ("protection_rules", []),
            ("deployment_branch_policy", None),
        ]:
            original = copy.deepcopy(self.environment)
            self.environment[key] = value
            with self.assertRaises(ValueError):
                self.check()
            self.environment = original
        self.reviews = []
        with self.assertRaises(ValueError):
            self.check()
        self.reviews = [{"state": "approved", "environments": [{"id": 9}]}]
        with self.assertRaises(ValueError):
            self.check()
        self.reviews = [{"state": "approved", "environments": [{"id": 7}]}]
        self.run["head_sha"] = N["git_sha"]
        with self.assertRaises(ValueError):
            self.check()

    def test_tag_and_wildcard_policies_are_rejected(self):
        for name, kind in [("main", "tag"), ("*", "branch"), ("release/*", "branch")]:
            self.policies["branch_policies"].append({"name": name, "type": kind})
            with self.assertRaises(ValueError):
                self.check()
            self.policies["branch_policies"].pop()


if __name__ == "__main__":
    unittest.main()
