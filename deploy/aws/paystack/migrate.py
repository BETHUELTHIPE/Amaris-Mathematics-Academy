"""Apply only the compatible Paystack migration on AWS staging."""

from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

project = "atyhhjwwxgzeurnwayay"
database = connection.settings_dict
host = database["HOST"]
assert connection.vendor == "postgresql"
assert host == f"db.{project}.supabase.co" or (
    host.endswith(".pooler.supabase.com") and database["USER"].endswith("." + project)
)
target = ("content", "0022_liveclass_paystack")
plan = MigrationExecutor(connection).migration_plan([target])
assert [(migration.app_label, migration.name, backwards) for migration, backwards in plan] in (
    [], [(*target, False)]
), "Unexpected database migration plan"
call_command("migrate", *target, interactive=False)
print("Paystack staging migration verified.")
