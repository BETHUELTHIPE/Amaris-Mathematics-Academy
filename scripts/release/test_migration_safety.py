from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from check_migration_safety import build_report
from verify_migration_plan import validate_plan


class MigrationSafetyScannerTests(unittest.TestCase):
    def write_migration(self, root: Path, body: str) -> None:
        migrations_dir = root / "sample" / "migrations"
        migrations_dir.mkdir(parents=True, exist_ok=True)
        (migrations_dir / "0001_test.py").write_text(body, encoding="utf-8")

    def test_safe_schema_addition_is_allowed(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_migration(
                root,
                "from django.db import migrations, models\n"
                "class Migration(migrations.Migration):\n"
                "    operations = [migrations.AddField(model_name='x', name='y', field=models.CharField(max_length=8, null=True))]\n",
            )
            report = build_report(root)
            self.assertFalse(report["destructive"])
            self.assertFalse(report["requires_backup"])

    def test_remove_field_is_blocked(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_migration(
                root,
                "from django.db import migrations\n"
                "class Migration(migrations.Migration):\n"
                "    operations = [migrations.RemoveField(model_name='x', name='y')]\n",
            )
            report = build_report(root)
            self.assertTrue(report["destructive"])
            self.assertEqual(report["status"], "blocked")

    def test_destructive_runsql_is_blocked(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_migration(
                root,
                "from django.db import migrations\n"
                "class Migration(migrations.Migration):\n"
                "    operations = [migrations.RunSQL('DROP TABLE legacy_records')]\n",
            )
            report = build_report(root)
            self.assertTrue(report["destructive"])

    def test_alter_field_requires_backup_review(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_migration(
                root,
                "from django.db import migrations, models\n"
                "class Migration(migrations.Migration):\n"
                "    operations = [migrations.AlterField(model_name='x', name='y', field=models.IntegerField())]\n",
            )
            report = build_report(root)
            self.assertFalse(report["destructive"])
            self.assertTrue(report["requires_backup"])

    def test_repository_migrations_have_no_destructive_operations(self):
        repo_root = Path(__file__).resolve().parents[2]
        report = build_report(repo_root / "backend")
        self.assertFalse(report["destructive"], report)


class RemoteMigrationPlanTests(unittest.TestCase):
    def safe_plan(self):
        return {
            "status": "ok",
            "destructive": False,
            "requires_backup": False,
            "reversible": True,
            "rollback_strategy": "reverse migration and previous immutable image",
        }

    def test_safe_staging_plan_passes(self):
        self.assertEqual(validate_plan(self.safe_plan(), "staging", False), [])

    def test_destructive_plan_is_blocked(self):
        plan = self.safe_plan()
        plan["destructive"] = True
        errors = validate_plan(plan, "staging", False)
        self.assertTrue(any("destructive" in error for error in errors))

    def test_production_backup_required_plan_needs_verified_backup(self):
        plan = self.safe_plan()
        plan["requires_backup"] = True
        errors = validate_plan(plan, "production", False)
        self.assertTrue(any("verified pre-migration backup" in error for error in errors))
        self.assertEqual(validate_plan(plan, "production", True), [])

    def test_irreversible_production_plan_needs_verified_backup(self):
        plan = self.safe_plan()
        plan["reversible"] = False
        errors = validate_plan(plan, "production", False)
        self.assertTrue(any("verified pre-migration backup" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
