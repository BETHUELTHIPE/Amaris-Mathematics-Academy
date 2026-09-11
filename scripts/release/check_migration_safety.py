#!/usr/bin/env python3
"""Fail closed when repository migrations contain destructive schema/data operations.

This is intentionally conservative. Destructive migrations must be redesigned into a
safe expand/migrate/contract sequence and are never auto-approved by CI.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Any

DESTRUCTIVE_OPERATIONS = {"DeleteModel", "RemoveField"}
BACKUP_REQUIRED_OPERATIONS = {
    "AlterField",
    "RenameField",
    "RenameModel",
    "RemoveConstraint",
    "RemoveIndex",
    "RunPython",
    "SeparateDatabaseAndState",
}
DESTRUCTIVE_SQL = re.compile(
    r"\b(?:DROP\s+(?:TABLE|COLUMN|INDEX|CONSTRAINT|SCHEMA|DATABASE)|TRUNCATE(?:\s+TABLE)?|DELETE\s+FROM)\b",
    re.IGNORECASE,
)


def operation_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def classify_call(call: ast.Call) -> tuple[str, str] | None:
    name = operation_name(call)
    if not name:
        return None

    if name in DESTRUCTIVE_OPERATIONS:
        return ("destructive", name)

    if name == "RunSQL":
        sql = literal_string(call.args[0]) if call.args else None
        if sql and DESTRUCTIVE_SQL.search(sql):
            return ("destructive", f"RunSQL:{sql.strip()[:120]}")
        return ("backup_required", "RunSQL requires manual data-impact review")

    if name in BACKUP_REQUIRED_OPERATIONS:
        return ("backup_required", name)

    return None


def scan_migration_file(path: Path) -> list[dict[str, Any]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    findings: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        classified = classify_call(node)
        if not classified:
            continue
        risk, operation = classified
        findings.append(
            {
                "file": str(path),
                "line": getattr(node, "lineno", None),
                "risk": risk,
                "operation": operation,
            }
        )
    return findings


def discover_migrations(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.glob("**/migrations/[0-9]*.py")
        if path.is_file()
    )


def build_report(root: Path) -> dict[str, Any]:
    files = discover_migrations(root)
    findings = [finding for path in files for finding in scan_migration_file(path)]
    destructive = [finding for finding in findings if finding["risk"] == "destructive"]
    backup_required = [
        finding for finding in findings if finding["risk"] == "backup_required"
    ]

    if destructive:
        status = "blocked"
        rollback = (
            "Automatic execution prohibited. Redesign as an expand/migrate/contract "
            "sequence; retain the previous immutable image and a verified database backup."
        )
    elif backup_required:
        status = "review-and-backup-required"
        rollback = (
            "Test forward and reverse behavior in staging. Production requires a verified "
            "pre-migration recovery point before promotion."
        )
    else:
        status = "safe"
        rollback = (
            "Use the previous immutable image for application rollback; validate Django "
            "reverse migration behavior in staging before production."
        )

    return {
        "status": status,
        "migration_files_scanned": len(files),
        "destructive": bool(destructive),
        "requires_backup": bool(backup_required),
        "destructive_operations": destructive,
        "backup_required_operations": backup_required,
        "rollback_strategy": rollback,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="backend", help="Repository subtree containing Django apps")
    parser.add_argument("--json-output", help="Optional report output path")
    args = parser.parse_args()

    report = build_report(Path(args.root))
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)

    if args.json_output:
        output = Path(args.json_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")

    return 2 if report["destructive"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
