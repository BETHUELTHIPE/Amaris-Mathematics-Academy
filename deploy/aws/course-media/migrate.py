"""Allow exactly the additive course media migration on the staging project."""
from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from content.services.course_media import s3_client

project = "atyhhjwwxgzeurnwayay"
database = connection.settings_dict
assert connection.vendor == "postgresql"
assert database["HOST"] == f"db.{project}.supabase.co" or (
    database["HOST"].endswith(".pooler.supabase.com") and database["USER"].endswith("." + project)
)
assert settings.ACADEMY_MEDIA_BUCKET == "amaris-mathematics-academy-media-stage-110156539003-eu-north-1"
s3_client().list_objects_v2(Bucket=settings.ACADEMY_MEDIA_BUCKET, Prefix="academy-media/", MaxKeys=1)
target = ("content", "0020_academy_course_media")
executor = MigrationExecutor(connection)
plan = [(migration.app_label, migration.name, backwards) for migration, backwards in executor.migration_plan([target])]
assert plan in ([], [(*target, False)]), "Unexpected database migration plan"
call_command("migrate", *target, interactive=False)
