from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).with_name("host_migration_plan.py")
SPEC = importlib.util.spec_from_file_location("host_migration_plan", MODULE_PATH)
assert SPEC and SPEC.loader
host_migration_plan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(host_migration_plan)


class HostMigrationPlanContractTests(unittest.TestCase):
    def valid_payload(self):
        sha = "a" * 40
        return {
            "action": "migration-plan",
            "environment": "staging",
            "image": f"docker.io/bethuelm/amaris-mathematics-academy:{sha}",
            "release_sha": sha,
        }

    def valid_plan(self):
        return {
            "status": "succeeded",
            "environment": "staging",
            "destructive": False,
            "requires_backup": False,
            "reversible": True,
            "rollback_strategy": "No pending migrations.",
            "pending_migrations": 0,
            "migrations": [],
        }

    def test_accepts_immutable_sha_tag_for_matching_environment(self):
        environment, image = host_migration_plan.validate_request(
            self.valid_payload(), "staging"
        )
        self.assertEqual(environment, "staging")
        self.assertTrue(image.endswith("a" * 40))

    def test_rejects_cross_environment_request(self):
        with self.assertRaises(host_migration_plan.ContractError):
            host_migration_plan.validate_request(self.valid_payload(), "production")

    def test_rejects_mutable_latest_tag(self):
        payload = self.valid_payload()
        payload["image"] = "docker.io/bethuelm/amaris-mathematics-academy:latest"
        with self.assertRaises(host_migration_plan.ContractError):
            host_migration_plan.validate_request(payload, "staging")

    def test_container_command_uses_argument_list_not_shell(self):
        command = host_migration_plan.build_container_command(
            self.valid_payload()["image"],
            "staging",
            Path("/run/amaris/staging.env"),
            "amaris-backend_backend_network",
        )
        self.assertEqual(command[0:2], ["docker", "run"])
        self.assertIn("--env-file", command)
        self.assertIn("--network", command)
        self.assertEqual(command[-2], "--entrypoint")
        self.assertEqual(command[-1].startswith("/app/ops/"), False)
        self.assertIn("/app/ops/migration-plan.sh", command)

    @mock.patch.object(host_migration_plan.subprocess, "run")
    def test_runs_candidate_image_and_returns_validated_plan(self, run):
        plan = self.valid_plan()
        run.side_effect = [
            mock.Mock(returncode=0),
            mock.Mock(returncode=0, stdout=json.dumps(plan), stderr=""),
        ]

        with tempfile.NamedTemporaryFile() as env_file:
            with mock.patch.dict(
                os.environ,
                {
                    "DEPLOYMENT_ENVIRONMENT": "staging",
                    "DEPLOYMENT_ENV_FILE": env_file.name,
                    "DEPLOYMENT_DOCKER_NETWORK": "amaris-backend_backend_network",
                },
                clear=False,
            ):
                result = host_migration_plan.run_migration_plan(self.valid_payload())

        self.assertEqual(result, plan)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0][0:2], ["docker", "pull"])
        container_command = run.call_args_list[1].args[0]
        self.assertIn("/app/ops/migration-plan.sh", container_command)
        self.assertNotIn("migrate", container_command)

    def test_rejects_incomplete_candidate_response(self):
        plan = self.valid_plan()
        del plan["rollback_strategy"]
        with self.assertRaises(host_migration_plan.ContractError):
            host_migration_plan.validate_plan_response(plan)


if __name__ == "__main__":
    unittest.main()
