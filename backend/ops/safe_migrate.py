#!/usr/bin/env python3
"""Production expansion migrations under one PostgreSQL advisory lock.

The adapter runs this in the candidate digest with --plan, then without --plan
after deployment. Contract/destructive/data migrations need a separate reviewed
maintenance procedure. Never reverse database migrations during image rollback.
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")


def compatible(operation):
    from django.db.migrations.operations import AddField, CreateModel

    return isinstance(operation, CreateModel) or (isinstance(operation, AddField) and operation.field.null)


def main():
    import django

    django.setup()
    from django.core.management import call_command
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    if connection.vendor != "postgresql":
        raise RuntimeError("Production migrations require PostgreSQL")
    plan_only = sys.argv[1:] == ["--plan"]
    if sys.argv[1:] and not plan_only:
        raise RuntimeError("Only --plan is supported")
    if not plan_only:
        if not os.environ.get("RECOVERY_ID"):
            raise RuntimeError("A verified pre-deployment recovery point is required")
        if not re.fullmatch(r"[0-9a-f]{40}", os.environ.get("APP_RELEASE_GIT_SHA", "")):
            raise RuntimeError("An exact release SHA is required")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", os.environ.get("RELEASE_DIGEST", "")):
            raise RuntimeError("An exact image digest is required")

    locked = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(147510139)")
            locked = cursor.fetchone()[0]
            if not locked:
                raise RuntimeError("Another migration holds the production database lock")
            cursor.execute("SET lock_timeout = '5s'")
            cursor.execute("SET statement_timeout = '120s'")
        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        plan = executor.migration_plan(targets)
        blocked = []
        for migration, backwards in plan:
            for operation in migration.operations:
                if backwards or not compatible(operation):
                    blocked.append(f"{migration.app_label}.{migration.name}:{type(operation).__name__}")
        if blocked:
            # Operation names only, never generated SQL or database contents.
            raise RuntimeError("Migration needs separate compatibility review: " + ", ".join(blocked))
        if plan_only:
            print(json.dumps({"backwards_compatible": True, "destructive": False, "pending": len(plan)}))
            return
        call_command("migrate", interactive=False, verbosity=0)
        remaining = MigrationExecutor(connection).migration_plan(targets)
        if remaining:
            raise RuntimeError("Pending migrations remain")
        print(json.dumps({"pending": 0, "backwards_compatible": True}))
    finally:
        if locked:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(147510139)")


if __name__ == "__main__":
    main()
