import subprocess
import sys
from copy import deepcopy
from pathlib import Path

from django.test import SimpleTestCase

from amaris_cms.database import validate_supabase_database


class SupabaseDatabaseConfigurationTests(SimpleTestCase):
    project_ref = "syntheticprojectref"
    project_url = f"https://{project_ref}.supabase.co"
    database = {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": "aws-1-example.pooler.supabase.com",
        "USER": f"amaris_staging_app.{project_ref}",
        "PORT": "5432",
        "OPTIONS": {"sslmode": "require"},
    }

    def test_session_pooler_with_custom_role_is_allowed(self):
        validate_supabase_database(self.database, self.project_url)

    def test_direct_project_connection_is_allowed(self):
        database = {**self.database, "HOST": f"db.{self.project_ref}.supabase.co", "USER": "amaris_staging_app"}
        validate_supabase_database(database, self.project_url)

    def test_explicit_project_ref_is_supported_without_auth_url(self):
        validate_supabase_database(self.database, "", self.project_ref)

    def test_other_databases_and_projects_are_rejected(self):
        for changes in (
            {"ENGINE": "django.db.backends.sqlite3"},
            {"HOST": "localhost"},
            {"HOST": "db.otherproject.supabase.co"},
            {"USER": "postgres.otherproject"},
            {"HOST": "aws-1-example.pooler.supabase.com.evil.example"},
            {"PORT": "6543"},
            {"OPTIONS": {}},
            {"OPTIONS": {"sslmode": "prefer"}},
        ):
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                validate_supabase_database({**deepcopy(self.database), **changes}, self.project_url)

    def test_auth_and_database_project_mismatch_is_rejected(self):
        with self.assertRaises(RuntimeError):
            validate_supabase_database(self.database, self.project_url, "differentproject")

    def test_missing_project_identity_is_rejected(self):
        with self.assertRaises(RuntimeError):
            validate_supabase_database(self.database, "")

    def settings_process(self, **overrides):
        return subprocess.run(
            [sys.executable, "-c", "import amaris_cms.settings"],
            cwd=Path(__file__).resolve().parents[1],
            env={
                "DJANGO_DEBUG": "true",
                "DJANGO_SECRET_KEY": "synthetic-settings-test-secret",
                "DATABASE_URL": "sqlite:///:memory:",
                "SUPABASE_URL": self.project_url,
                "SUPABASE_DATABASE_REQUIRED": "false",
                **overrides,
            },
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_render_cannot_disable_supabase_requirement_with_local_env_flag(self):
        result = self.settings_process(RENDER="true")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("The deployed database must use Supabase PostgreSQL", result.stderr)

    def test_debug_false_rejects_sqlite_even_with_explicit_url(self):
        result = self.settings_process(DJANGO_DEBUG="false")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PostgreSQL is required", result.stderr)

    def test_render_accepts_valid_supabase_settings_without_connecting(self):
        result = self.settings_process(
            RENDER="true",
            DATABASE_URL=(
                f"postgresql://amaris_staging_app.{self.project_ref}:synthetic-only"
                "@aws-1-example.pooler.supabase.com:5432/postgres"
            ),
            DATABASE_SSL_REQUIRED="true",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
