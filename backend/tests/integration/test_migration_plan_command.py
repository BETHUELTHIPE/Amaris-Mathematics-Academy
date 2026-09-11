from __future__ import annotations

import json
from io import StringIO

from django.core.management import call_command
from django.db import migrations, models
from django.test import SimpleTestCase, TestCase

from content.management.commands.migration_plan import classify_operation


class MigrationOperationClassificationTests(SimpleTestCase):
    def test_add_field_is_not_destructive(self):
        operation = migrations.AddField(
            model_name="example",
            name="label",
            field=models.CharField(max_length=20, null=True),
        )

        result = classify_operation(operation)

        self.assertFalse(result["destructive"])
        self.assertFalse(result["requires_backup"])
        self.assertTrue(result["reversible"])

    def test_remove_field_is_blocked_as_destructive(self):
        result = classify_operation(migrations.RemoveField(model_name="example", name="legacy_value"))

        self.assertTrue(result["destructive"])

    def test_destructive_runsql_is_blocked(self):
        result = classify_operation(
            migrations.RunSQL(
                "DROP TABLE legacy_records",
                reverse_sql="CREATE TABLE legacy_records (id integer)",
            )
        )

        self.assertTrue(result["destructive"])
        self.assertTrue(result["requires_backup"])

    def test_alter_field_requires_backup_review(self):
        result = classify_operation(
            migrations.AlterField(
                model_name="example",
                name="label",
                field=models.CharField(max_length=10),
            )
        )

        self.assertFalse(result["destructive"])
        self.assertTrue(result["requires_backup"])


class MigrationPlanCommandTests(TestCase):
    def test_json_contract_is_machine_readable_and_read_only(self):
        stdout = StringIO()

        call_command(
            "migration_plan",
            environment="staging",
            json=True,
            stdout=stdout,
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(payload["environment"], "staging")
        self.assertIsInstance(payload["destructive"], bool)
        self.assertIsInstance(payload["requires_backup"], bool)
        self.assertIsInstance(payload["reversible"], bool)
        self.assertIsInstance(payload["rollback_strategy"], str)
        self.assertTrue(payload["rollback_strategy"])
        self.assertIsInstance(payload["pending_migrations"], int)
        self.assertIsInstance(payload["migrations"], list)
