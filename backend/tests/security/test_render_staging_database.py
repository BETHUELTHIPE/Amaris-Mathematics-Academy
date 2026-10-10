"""Ensure only the dedicated staging service can use Render PostgreSQL."""

from unittest import TestCase

from amaris_cms.database import (
    is_render_staging_service,
    validate_render_staging_database,
)


class RenderStagingDatabaseTests(TestCase):
    def setUp(self):
        self.database = {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": "dpg-dam2gj6k1f9s73e81tmg-a",
            "PORT": 5432,
            "NAME": "amaris_staging_postgres",
            "USER": "amaris_staging_postgres_user",
        }

    def test_identified_staging_service_is_allowed(self):
        self.assertTrue(is_render_staging_service("srv-dam2iivcgkoc7383tq50", "staging"))
        validate_render_staging_database(self.database)

    def test_production_or_other_service_is_not_staging(self):
        self.assertFalse(is_render_staging_service("srv-dapn6b3tqb8s73d3r7n0", "production-release-20260923"))
        self.assertFalse(is_render_staging_service("srv-dam2iivcgkoc7383tq50", "main"))
        self.assertFalse(is_render_staging_service("", "staging"))

    def test_supabase_database_is_rejected_in_staging(self):
        self.database["HOST"] = "aws-1-us-east-1.pooler.supabase.com"
        with self.assertRaisesRegex(RuntimeError, "Render"):
            validate_render_staging_database(self.database)

    def test_other_render_database_is_rejected(self):
        self.database["HOST"] = "dpg-dapagkpsrm7s73eoaagg-a"
        with self.assertRaisesRegex(RuntimeError, "Render"):
            validate_render_staging_database(self.database)

    def test_deceptive_hostname_suffix_is_rejected(self):
        self.database["HOST"] += ".attacker.example"
        with self.assertRaisesRegex(RuntimeError, "Render"):
            validate_render_staging_database(self.database)

    def test_wrong_database_name_is_rejected(self):
        self.database["NAME"] = "amaris_production_postgres"
        with self.assertRaisesRegex(RuntimeError, "database name"):
            validate_render_staging_database(self.database)

    def test_wrong_database_user_is_rejected(self):
        self.database["USER"] = "other_user"
        with self.assertRaisesRegex(RuntimeError, "database user"):
            validate_render_staging_database(self.database)

    def test_sqlite_is_rejected(self):
        self.database["ENGINE"] = "django.db.backends.sqlite3"
        with self.assertRaisesRegex(RuntimeError, "Render PostgreSQL"):
            validate_render_staging_database(self.database)

    def test_wrong_port_is_rejected(self):
        self.database["PORT"] = 6432
        with self.assertRaisesRegex(RuntimeError, "port 5432"):
            validate_render_staging_database(self.database)
