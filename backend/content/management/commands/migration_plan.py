from __future__ import annotations

import json
import re
from typing import Any

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

DESTRUCTIVE_OPERATION_NAMES = {"DeleteModel", "RemoveField"}
BACKUP_REQUIRED_OPERATION_NAMES = {
    "AlterField",
    "RenameField",
    "RenameModel",
    "RemoveConstraint",
    "RemoveIndex",
    "RunPython",
    "SeparateDatabaseAndState",
}
DESTRUCTIVE_SQL = re.compile(
    r"\b(?:DROP\s+(?:TABLE|COLUMN|INDEX|CONSTRAINT|SCHEMA|DATABASE)|"
    r"TRUNCATE(?:\s+TABLE)?|DELETE\s+FROM)\b",
    re.IGNORECASE,
)


def _sql_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, (list, tuple)) and item and isinstance(item[0], str):
                parts.append(item[0])
        return "\n".join(parts)
    return ""


def classify_operation(operation: Any) -> dict[str, Any]:
    name = operation.__class__.__name__
    destructive = name in DESTRUCTIVE_OPERATION_NAMES
    requires_backup = name in BACKUP_REQUIRED_OPERATION_NAMES

    if name == "RunSQL":
        sql = _sql_text(getattr(operation, "sql", ""))
        destructive = bool(DESTRUCTIVE_SQL.search(sql))
        requires_backup = True

    reversible = bool(getattr(operation, "reversible", True))
    return {
        "operation": name,
        "destructive": destructive,
        "requires_backup": requires_backup,
        "reversible": reversible,
    }


def build_migration_plan() -> dict[str, Any]:
    executor = MigrationExecutor(connection)
    targets = executor.loader.graph.leaf_nodes()
    planned = executor.migration_plan(targets)

    migrations: list[dict[str, Any]] = []
    destructive = False
    requires_backup = False
    reversible = True

    for migration, backwards in planned:
        operations: list[dict[str, Any]] = []
        for operation in migration.operations:
            classification = classify_operation(operation)
            operations.append(classification)
            destructive = destructive or classification["destructive"]
            requires_backup = requires_backup or classification["requires_backup"]
            reversible = reversible and classification["reversible"]

        migrations.append(
            {
                "app": migration.app_label,
                "name": migration.name,
                "backwards": bool(backwards),
                "operations": operations,
            }
        )

    if destructive:
        rollback_strategy = (
            "Automatic execution is prohibited. Redesign the schema change using an "
            "expand/migrate/contract sequence and retain the previous immutable image plus "
            "a verified database recovery point."
        )
    elif requires_backup or not reversible:
        rollback_strategy = (
            "Create and verify a pre-migration database recovery point before production. "
            "Application rollback uses the previous immutable image; database recovery uses "
            "the verified recovery point if forward correction is unsafe."
        )
    elif migrations:
        rollback_strategy = (
            "Validate the forward migration and Django reverse migration in staging. "
            "Application rollback uses the previous immutable image."
        )
    else:
        rollback_strategy = "No pending database migrations for this candidate image."

    return {
        "status": "succeeded",
        "destructive": destructive,
        "requires_backup": requires_backup,
        "reversible": reversible,
        "rollback_strategy": rollback_strategy,
        "pending_migrations": len(migrations),
        "migrations": migrations,
    }


class Command(BaseCommand):
    help = "Emit a read-only JSON migration plan for deployment safety checks."

    def add_arguments(self, parser):
        parser.add_argument(
            "--environment",
            choices=("staging", "production"),
            default="staging",
            help="Target environment included in the JSON report.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit machine-readable JSON (the deployment webhook contract).",
        )

    def handle(self, *args, **options):
        report = build_migration_plan()
        report["environment"] = options["environment"]

        if options["json"]:
            self.stdout.write(json.dumps(report, sort_keys=True))
            return

        self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
