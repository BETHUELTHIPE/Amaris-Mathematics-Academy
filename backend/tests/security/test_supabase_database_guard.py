"""Supabase-only production routing regression tests (no network or credentials)."""

from django.test import SimpleTestCase

from amaris_cms.database_guard import validate_supabase_database_url

REF = "epkcuseloinygkakxxdu"
DIRECT = f"postgresql://postgres:synthetic-password@db.{REF}.supabase.co:5432/postgres"
SESSION = f"postgresql://postgres.{REF}:synthetic-password@aws-1-us-east-1.pooler.supabase.com:5432/postgres"


class SupabaseOnlyDatabaseGuardTests(SimpleTestCase):
    def check_url(self, url: str, ssl_required: bool = True) -> None:
        validate_supabase_database_url(url, ssl_required=ssl_required, project_ref=REF)

    def test_direct_supabase_connection(self):
        self.check_url(DIRECT)

    def test_session_pooler_connection(self):
        self.check_url(SESSION)

    def test_rejects_unrelated_database_and_sqlite(self):
        for url in (
            "sqlite:///db.sqlite3",
            "postgresql://user:password@render-postgres.internal:5432/amaris",
            f"postgresql://postgres:password@db.otherproject.supabase.co:5432/postgres",
            "",
        ):
            with self.subTest(url=url.split("@")[-1]), self.assertRaises(RuntimeError):
                self.check_url(url)

    def test_rejects_transaction_pooling(self):
        with self.assertRaisesRegex(RuntimeError, "port 5432"):
            self.check_url(SESSION.replace(":5432/", ":6543/"))

    def test_rejects_wrong_pooler_username(self):
        with self.assertRaises(RuntimeError):
            self.check_url(SESSION.replace(f"postgres.{REF}:", "postgres.otherproject:"))

    def test_rejects_unencrypted_database(self):
        with self.assertRaisesRegex(RuntimeError, "DATABASE_SSL_REQUIRED"):
            self.check_url(DIRECT, ssl_required=False)

    def test_rejects_missing_password(self):
        with self.assertRaises(RuntimeError):
            self.check_url(DIRECT.replace("synthetic-password", ""))
