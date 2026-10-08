"""Unit tests for unattended database-migration safety."""

from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.db import migrations, models
from django.test import SimpleTestCase

from content.management.commands.safe_migrate import blocked_operations


def migration_with(*operations):
    migration = migrations.Migration("0002_release_test", "content")
    migration.operations = list(operations)
    return migration


class SafeMigrationTests(SimpleTestCase):
    def test_additive_migrations_can_run_unattended(self):
        safe_plan = [
            (
                migration_with(
                    migrations.CreateModel(
                        name="ReleaseEvidence",
                        fields=[("id", models.AutoField(primary_key=True))],
                    ),
                    migrations.AddField(
                        model_name="re",
                        name="note",
                        field=models.CharField(default="", max_length=64),
                    ),
                    migrations.AddIndex(
                        model_name="re",
                        index=models.Index(fields=["note"], name="release_note_idx"),
                    ),
                ),
                False,
            )
        ]
        self.assertEqual(blocked_operations(safe_plan), [])

    def test_removal_and_custom_sql_block_automatic_migration(self):
        plan = [
            (
                migration_with(
                    migrations.RemoveField(model_name="course", name="title"),
                    migrations.RunSQL("DROP TABLE content_course"),
                ),
                False,
            )
        ]
        self.assertEqual(blocked_operations(plan), ["RemoveField", "RunSQL"])

    def test_data_backfill_and_field_alteration_require_manual_review(self):
        plan = [
            (
                migration_with(
                    migrations.RunPython(migrations.RunPython.noop),
                    migrations.AlterField(
                        model_name="course",
                        name="title",
                        field=models.TextField(),
                    ),
                ),
                False,
            )
        ]
        self.assertEqual(blocked_operations(plan), ["RunPython", "AlterField"])

    def test_reverse_migrations_are_never_run_automatically(self):
        plan = [(migration_with(migrations.CreateModel(name="Trial", fields=[])), True)]
        self.assertIn("reverse migration", blocked_operations(plan))

    @patch("content.management.commands.safe_migrate.MigrationExecutor")
    @patch("content.management.commands.safe_migrate.connection")
    @patch("content.management.commands.safe_migrate.call_command")
    def test_safe_command_checks_post_migration_state(self, inner_command, database, executor):
        database.vendor = "postgresql"
        executor.return_value.migration_plan.return_value = []
        call_command("safe_migrate", verbosity=0)
        inner_command.assert_called_once_with("migrate", interactive=False, verbosity=0)

    @patch("content.management.commands.safe_migrate.MigrationExecutor")
    @patch("content.management.commands.safe_migrate.connection")
    @patch("content.management.commands.safe_migrate.call_command")
    def test_dangerous_plan_does_not_call_migrate(self, inner_command, database, executor):
        database.vendor = "postgresql"
        executor.return_value.migration_plan.return_value = [
            (migration_with(migrations.RemoveField(model_name="course", name="title")), False)
        ]
        with self.assertRaises(CommandError):
            call_command("safe_migrate", verbosity=0)
        inner_command.assert_not_called()
