import unittest
from verify_staging_database_isolation import (
    is_dedicated_supabase_staging_dsn,
    validate_dedicated_staging_facts,
)

PROJECT = "atyhhjwwxgzeurnwayay"
PRODUCTION = "epkcuseloinygkakxxdu"

class DedicatedStagingDatabasePolicyTests(unittest.TestCase):
    def test_staging_pooler_and_direct_host_are_identified(self):
        for dsn in (
            f"postgresql://postgres.{PROJECT}:SYNTHETIC@aws-0-eu-west-1.pooler.supabase.com:5432/postgres",
            f"postgresql://postgres.{PROJECT}:SYNTHETIC@aws-0-eu-west-1.pooler.supabase.com:6543/postgres",
            f"postgresql://postgres:SYNTHETIC@db.{PROJECT}.supabase.co:5432/postgres",
        ):
            self.assertTrue(is_dedicated_supabase_staging_dsn(dsn))

    def test_production_and_unknown_connections_are_never_accepted(self):
        bad = (
            f"postgresql://postgres.{PRODUCTION}:SYNTHETIC@aws-0-eu-west-1.pooler.supabase.com:5432/postgres",
            f"postgresql://postgres:SYNTHETIC@db.{PRODUCTION}.supabase.co:5432/postgres",
            f"postgresql://postgres.{PROJECT}:SYNTHETIC@host.invalid:5432/postgres",
            f"postgresql://postgres.{PROJECT}@aws-0-eu-west-1.pooler.supabase.com:5432/postgres",
            f"postgresql://postgres.{PROJECT}:SYNTHETIC@aws-0-eu-west-1.pooler.supabase.com:5432/other",
            "sqlite:///production.db",
        )
        for dsn in bad:
            self.assertFalse(is_dedicated_supabase_staging_dsn(dsn))

    def test_database_user_name_and_schema_all_must_match(self):
        good = {"database_name": "postgres", "database_role": "postgres", "schema_name": "public"}
        self.assertTrue(validate_dedicated_staging_facts(good))
        for key in good:
            wrong = dict(good)
            wrong[key] = "wrong"
            self.assertFalse(validate_dedicated_staging_facts(wrong))

if __name__ == "__main__":
    unittest.main()
