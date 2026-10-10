from django.test import SimpleTestCase

from amaris_cms.database import requires_supabase_database


class SupabaseDeploymentDatabaseGateTests(SimpleTestCase):
    def test_render_requires_supabase_by_default(self):
        self.assertTrue(requires_supabase_database({"RENDER": "true"}))

    def test_render_production_cannot_disable_supabase_requirement(self):
        self.assertTrue(
            requires_supabase_database(
                {
                    "RENDER": "true",
                    "AMARIS_DEPLOYMENT_ENVIRONMENT": "production",
                    "SUPABASE_DATABASE_REQUIRED": "false",
                }
            )
        )

    def test_render_staging_requires_explicit_opt_out(self):
        self.assertTrue(requires_supabase_database({"RENDER": "true", "AMARIS_DEPLOYMENT_ENVIRONMENT": "staging"}))

    def test_render_staging_can_use_separate_postgres(self):
        self.assertFalse(
            requires_supabase_database(
                {
                    "RENDER": "true",
                    "AMARIS_DEPLOYMENT_ENVIRONMENT": "staging",
                    "SUPABASE_DATABASE_REQUIRED": "false",
                }
            )
        )

    def test_local_test_database_remains_supported(self):
        self.assertFalse(requires_supabase_database({}))

    def test_explicit_supabase_requirement_applies_outside_render(self):
        self.assertTrue(requires_supabase_database({"SUPABASE_DATABASE_REQUIRED": "yes"}))
