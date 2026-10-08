"""Fail-closed migration entrypoint for unattended staging/production deployments.

Only explicitly additive schema operations are allowed automatically. Any
destructive, data, custom SQL, or unknown operation requires a separately
reviewed migration procedure with a verified backup.
"""

from django.core.management import BaseCommand, CommandError, call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.operations.fields import AddField
from django.db.migrations.operations.models import AddIndex, CreateModel

AUTOMATICALLY_SAFE_OPERATIONS = (AddField, AddIndex, CreateModel)


def blocked_operations(plan):
    """Return operation types requiring manual review, without leaking SQL."""
    blocked = []
    for migration, backwards in plan:
        if backwards:
            blocked.append("reverse migration")
        for operation in migration.operations:
            if not isinstance(operation, AUTOMATICALLY_SAFE_OPERATIONS):
                blocked.append(type(operation).__name__)
    return blocked


class Command(BaseCommand):
    help = "Apply only reviewed additive migrations against PostgreSQL."

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("Automatic migrations require PostgreSQL.")

        try:
            executor = MigrationExecutor(connection)
            pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
        except Exception as exc:
            raise CommandError("Could not inspect PostgreSQL migration plan.") from exc

        blockers = blocked_operations(pending)
        if blockers:
            unique = ", ".join(sorted(set(blockers)))
            raise CommandError(
                "Automatic migration blocked: manual review and backup required "
                f"for operation types: {unique}."
            )

        self.stdout.write(f"Safe migration preflight passed ({len(pending)} pending).")
        call_command("migrate", interactive=False, verbosity=options["verbosity"])

        try:
            verification = MigrationExecutor(connection)
            remaining = verification.migration_plan(verification.loader.graph.leaf_nodes())
        except Exception as exc:
            raise CommandError("Could not verify post-migration schema.") from exc
        if remaining:
            raise CommandError("Post-migration verification found unapplied migrations.")
        self.stdout.write(self.style.SUCCESS("PostgreSQL schema is up to date."))
