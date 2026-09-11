from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).with_name("deployment_webhook_server.py")
SPEC = importlib.util.spec_from_file_location("deployment_webhook_server", MODULE_PATH)
assert SPEC and SPEC.loader
deployment_webhook_server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deployment_webhook_server)


class DeploymentWebhookDispatchTests(unittest.TestCase):
    def valid_payload(self, action: str = "migration-plan"):
        sha = "b" * 40
        return {
            "action": action,
            "environment": "staging",
            "image": f"docker.io/bethuelm/amaris-mathematics-academy:{sha}",
            "release_sha": sha,
        }

    @mock.patch.object(
        deployment_webhook_server.host_migration_plan,
        "run_migration_plan",
        return_value={
            "status": "succeeded",
            "environment": "staging",
            "destructive": False,
            "requires_backup": False,
            "reversible": True,
            "rollback_strategy": "No pending migrations.",
            "pending_migrations": 0,
            "migrations": [],
        },
    )
    def test_migration_plan_is_dispatched_to_read_only_adapter(self, run_plan):
        with mock.patch.dict(os.environ, {"DEPLOYMENT_ENVIRONMENT": "staging"}, clear=False):
            result = deployment_webhook_server.dispatch(self.valid_payload())

        self.assertEqual(result["status"], "succeeded")
        run_plan.assert_called_once_with(self.valid_payload())

    def test_cross_environment_request_is_rejected(self):
        with mock.patch.dict(os.environ, {"DEPLOYMENT_ENVIRONMENT": "production"}, clear=False):
            with self.assertRaises(deployment_webhook_server.WebhookError):
                deployment_webhook_server.dispatch(self.valid_payload())

    @mock.patch.object(deployment_webhook_server.subprocess, "run")
    def test_existing_actions_delegate_to_fixed_executable_without_shell(self, run):
        run.return_value = mock.Mock(
            returncode=0,
            stdout=json.dumps({"status": "succeeded"}),
            stderr="",
        )
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "deploy-handler"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o700)
            with mock.patch.dict(
                os.environ,
                {
                    "DEPLOYMENT_ENVIRONMENT": "staging",
                    "DEPLOY_ACTION_EXECUTABLE": str(executable),
                },
                clear=False,
            ):
                result = deployment_webhook_server.dispatch(self.valid_payload("deploy"))

        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(run.call_args.args[0], [str(executable)])
        self.assertNotIn("shell", run.call_args.kwargs)
        delegated_payload = json.loads(run.call_args.kwargs["input"])
        self.assertEqual(delegated_payload["action"], "deploy")

    def test_unknown_action_is_rejected(self):
        payload = self.valid_payload()
        payload["action"] = "shell"
        with mock.patch.dict(os.environ, {"DEPLOYMENT_ENVIRONMENT": "staging"}, clear=False):
            with self.assertRaises(deployment_webhook_server.WebhookError):
                deployment_webhook_server.dispatch(payload)


if __name__ == "__main__":
    unittest.main()
