#!/usr/bin/env python3
"""Server-side adapter for the deployment webhook `migration-plan` action.

The existing HTTPS webhook should authenticate the request, then pass the JSON body to
this program on stdin. This adapter validates environment and immutable image identity,
pulls the candidate image, and executes its read-only migration-plan entrypoint against
the target environment's database configuration.

It never invokes a shell and never executes Django `migrate`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

IMAGE_PREFIX = "docker.io/bethuelm/amaris-mathematics-academy:"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SUCCESS_STATES = {"ok", "completed", "succeeded"}


class ContractError(ValueError):
    pass


def validate_request(payload: dict[str, Any], configured_environment: str) -> tuple[str, str]:
    if payload.get("action") != "migration-plan":
        raise ContractError("action must be migration-plan")

    environment = payload.get("environment")
    if environment not in {"staging", "production"}:
        raise ContractError("environment must be staging or production")
    if environment != configured_environment:
        raise ContractError("request environment does not match this deployment host")

    image = payload.get("image")
    release_sha = payload.get("release_sha")
    if not isinstance(image, str) or not image.startswith(IMAGE_PREFIX):
        raise ContractError("image must use the approved Amaris Docker Hub repository")
    if not isinstance(release_sha, str) or not SHA_RE.fullmatch(release_sha):
        raise ContractError("release_sha must be a full 40-character lowercase git SHA")

    image_tag = image.removeprefix(IMAGE_PREFIX)
    if image_tag != release_sha:
        raise ContractError("image tag must exactly match release_sha")

    return environment, image


def validate_plan_response(plan: Any) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise ContractError("candidate migration plan must be a JSON object")
    if plan.get("status") not in SUCCESS_STATES:
        raise ContractError("candidate migration plan status is not successful")

    for field in ("destructive", "requires_backup", "reversible"):
        if not isinstance(plan.get(field), bool):
            raise ContractError(f"candidate migration plan must include boolean {field}")

    rollback_strategy = plan.get("rollback_strategy")
    if not isinstance(rollback_strategy, str) or not rollback_strategy.strip():
        raise ContractError("candidate migration plan must include rollback_strategy")

    if not isinstance(plan.get("pending_migrations"), int):
        raise ContractError("candidate migration plan must include pending_migrations")
    if not isinstance(plan.get("migrations"), list):
        raise ContractError("candidate migration plan must include migrations")

    return plan


def build_container_command(
    image: str,
    environment: str,
    env_file: Path,
    network: str | None,
) -> list[str]:
    command = [
        "docker",
        "run",
        "--rm",
        "--env-file",
        str(env_file),
        "--env",
        f"DEPLOYMENT_ENVIRONMENT={environment}",
    ]
    if network:
        command.extend(["--network", network])
    command.extend(["--entrypoint", "/app/ops/migration-plan.sh", image])
    return command


def run_migration_plan(payload: dict[str, Any]) -> dict[str, Any]:
    configured_environment = os.environ.get("DEPLOYMENT_ENVIRONMENT", "")
    if configured_environment not in {"staging", "production"}:
        raise ContractError("DEPLOYMENT_ENVIRONMENT must be staging or production")

    environment, image = validate_request(payload, configured_environment)

    env_file_value = os.environ.get("DEPLOYMENT_ENV_FILE", "")
    if not env_file_value:
        raise ContractError("DEPLOYMENT_ENV_FILE is required")
    env_file = Path(env_file_value)
    if not env_file.is_file():
        raise ContractError("DEPLOYMENT_ENV_FILE does not exist")

    network = os.environ.get("DEPLOYMENT_DOCKER_NETWORK") or None

    subprocess.run(
        ["docker", "pull", image],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        timeout=300,
    )

    completed = subprocess.run(
        build_container_command(image, environment, env_file, network),
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )

    try:
        plan = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ContractError("candidate image returned invalid migration-plan JSON") from exc

    validated = validate_plan_response(plan)
    if validated.get("environment") != environment:
        raise ContractError("candidate migration plan environment mismatch")
    return validated


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ContractError("request body must be a JSON object")
        result = run_migration_plan(payload)
    except (ContractError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}), file=sys.stderr)
        return 2

    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
