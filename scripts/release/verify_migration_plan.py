#!/usr/bin/env python3
"""Validate a deployment service migration-plan response.

Expected JSON fields:
- status: ok/completed/succeeded
- destructive: boolean
- requires_backup: boolean
- reversible: boolean
- rollback_strategy: non-empty string

Production plans that require a backup or are not reversible are blocked unless the
pre-migration backup step has already set PRE_MIGRATION_BACKUP_VERIFIED=true.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

SUCCESS_STATES = {"ok", "completed", "succeeded"}


def validate_plan(plan: dict[str, Any], environment: str, backup_verified: bool) -> list[str]:
    errors: list[str] = []

    if plan.get("status") not in SUCCESS_STATES:
        errors.append("migration plan status is not successful")

    destructive = plan.get("destructive")
    requires_backup = plan.get("requires_backup")
    reversible = plan.get("reversible")
    rollback_strategy = plan.get("rollback_strategy")

    if not isinstance(destructive, bool):
        errors.append("migration plan must include boolean destructive")
    elif destructive:
        errors.append("destructive migration operations are blocked from automatic execution")

    if not isinstance(requires_backup, bool):
        errors.append("migration plan must include boolean requires_backup")

    if not isinstance(reversible, bool):
        errors.append("migration plan must include boolean reversible")

    if not isinstance(rollback_strategy, str) or not rollback_strategy.strip():
        errors.append("migration plan must include a rollback_strategy")

    if environment == "production" and isinstance(requires_backup, bool) and isinstance(reversible, bool):
        if (requires_backup or not reversible) and not backup_verified:
            errors.append("production migration requires a verified pre-migration backup")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("environment", choices=["staging", "production"])
    parser.add_argument("--file", help="Read plan JSON from file instead of stdin")
    args = parser.parse_args()

    try:
        raw = open(args.file, encoding="utf-8").read() if args.file else sys.stdin.read()
        plan = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Invalid migration plan response: {exc}", file=sys.stderr)
        return 2

    if not isinstance(plan, dict):
        print("Migration plan response must be a JSON object.", file=sys.stderr)
        return 2

    backup_verified = os.getenv("PRE_MIGRATION_BACKUP_VERIFIED", "false").lower() == "true"
    errors = validate_plan(plan, args.environment, backup_verified)
    if errors:
        for error in errors:
            print(f"Migration safety gate: {error}", file=sys.stderr)
        return 2

    print("Migration plan safety gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
