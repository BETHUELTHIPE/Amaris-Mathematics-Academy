import importlib.util
import unittest
from pathlib import Path


@unittest.skipUnless(importlib.util.find_spec("django"), "Django dependencies are installed in backend CI")
class SafeMigrationTests(unittest.TestCase):
    def test_only_compatible_expansions_are_accepted(self):
        from django.db import migrations, models

        path = Path(__file__).resolve().parents[2] / "backend/ops/safe_migrate.py"
        spec = importlib.util.spec_from_file_location("safe_migrate", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(module.compatible(migrations.CreateModel("NewTable", fields=[])))
        self.assertTrue(module.compatible(migrations.AddField("course", "subtitle", models.TextField(null=True))))
        for operation in [
            migrations.AddField("course", "required_value", models.IntegerField()),
            migrations.RemoveField("course", "title"),
            migrations.DeleteModel("Course"),
            migrations.RenameField("course", "title", "name"),
            migrations.AlterField("course", "title", models.TextField()),
            migrations.RunPython(migrations.RunPython.noop),
            migrations.RunSQL("DROP TABLE course"),
        ]:
            with self.subTest(operation=type(operation).__name__):
                self.assertFalse(module.compatible(operation))
