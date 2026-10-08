from django.test import SimpleTestCase

from amaris_cms.database_policy import assert_supabase_database


class SupabaseDatabasePolicyTests(SimpleTestCase):
    project_ref = "epkcuseloinygkakxxdu"

    def test_accepts_direct_supabase_connection(self):
        assert_supabase_database(
            {
                "ENGINE": "django.db.backends.postgresql",
                "HOST": f"db.{self.project_ref}.supabase.co",
                "USER": "postgres",
            },
            self.project_ref,
        )

    def test_accepts_supabase_session_pooler_connection(self):
        assert_supabase_database(
            {
                "ENGINE": "django.db.backends.postgresql",
                "HOST": "aws-1-us-east-1.pooler.supabase.com",
                "USER": f"postgres.{self.project_ref}",
            },
            self.project_ref,
        )

    def test_rejects_render_postgres(self):
        with self.assertRaises(RuntimeError):
            assert_supabase_database(
                {
                    "ENGINE": "django.db.backends.postgresql",
                    "HOST": "dpg-example-a.frankfurt-postgres.render.com",
                    "USER": "amaris",
                },
                self.project_ref,
            )

    def test_rejects_different_supabase_project(self):
        with self.assertRaises(RuntimeError):
            assert_supabase_database(
                {
                    "ENGINE": "django.db.backends.postgresql",
                    "HOST": "aws-1-us-east-1.pooler.supabase.com",
                    "USER": "postgres.otherproject",
                },
                self.project_ref,
            )

    def test_rejects_sqlite(self):
        with self.assertRaises(RuntimeError):
            assert_supabase_database(
                {"ENGINE": "django.db.backends.sqlite3", "HOST": "", "USER": ""},
                self.project_ref,
            )

    def test_requires_project_ref(self):
        with self.assertRaises(RuntimeError):
            assert_supabase_database(
                {
                    "ENGINE": "django.db.backends.postgresql",
                    "HOST": "aws-1-us-east-1.pooler.supabase.com",
                    "USER": f"postgres.{self.project_ref}",
                },
                "",
            )
