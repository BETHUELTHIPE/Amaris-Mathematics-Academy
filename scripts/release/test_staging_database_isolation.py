"""Offline release-gate tests; never connect to a real database."""

import unittest

from verify_staging_database_isolation import (
    is_isolated_render_staging_dsn,
    validate_facts,
    validate_render_facts,
)


class StagingDatabaseIsolationTests(unittest.TestCase):
    def setUp(self):
        self.safe = {
            "current_user": "amaris_staging_app",
            "current_schema": "amaris_staging",
            "search_path": "amaris_staging, public",
            "staging_schema_exists": True,
            "staging_schema_creatable": True,
            "public_schema_creatable": False,
            "public_readable_tables": 0,
            "public_writable_tables": 0,
        }

    def test_safe_role_and_schema(self):
        self.assertTrue(validate_facts(self.safe)[0])

    def test_production_role_is_rejected(self):
        self.assertFalse(validate_facts({**self.safe, "current_user": "postgres"})[0])

    def test_public_schema_is_rejected(self):
        self.assertFalse(validate_facts({**self.safe, "current_schema": "public"})[0])

    def test_wrong_search_path_is_rejected(self):
        self.assertFalse(
            validate_facts({**self.safe, "search_path": "public, amaris_staging"})[0]
        )

    def test_any_public_write_privilege_is_rejected(self):
        self.assertFalse(validate_facts({**self.safe, "public_writable_tables": 1})[0])
        self.assertFalse(
            validate_facts({**self.safe, "public_schema_creatable": True})[0]
        )

    def test_public_read_access_is_rejected(self):
        self.assertFalse(validate_facts({**self.safe, "public_readable_tables": 1})[0])

    def test_missing_or_unwritable_staging_schema_is_rejected(self):
        self.assertFalse(
            validate_facts({**self.safe, "staging_schema_exists": False})[0]
        )
        self.assertFalse(
            validate_facts({**self.safe, "staging_schema_creatable": False})[0]
        )

    def test_exact_separate_render_staging_resource_is_allowed(self):
        url = "postgresql://amaris_staging_postgres_user:synthetic-password@dpg-dam2gj6k1f9s73e81tmg-a:5432/amaris_staging_postgres"
        self.assertTrue(is_isolated_render_staging_dsn(url))
        self.assertFalse(
            is_isolated_render_staging_dsn(
                url.replace("dpg-dam2gj6k1f9s73e81tmg-a", "dpg-other-database")
            )
        )
        self.assertFalse(
            is_isolated_render_staging_dsn(
                url.replace(
                    "dpg-dam2gj6k1f9s73e81tmg-a", "dpg-dam2gj6k1f9s73e81tmg-a.evil.test"
                )
            )
        )
        self.assertFalse(
            is_isolated_render_staging_dsn(
                url.replace("/amaris_staging_postgres", "/postgres")
            )
        )
        self.assertFalse(
            is_isolated_render_staging_dsn(
                url.replace("amaris_staging_postgres_user", "postgres")
            )
        )
        self.assertFalse(
            is_isolated_render_staging_dsn(url.replace(":synthetic-password", ""))
        )

    def test_render_runtime_facts_must_match_the_isolated_resource(self):
        safe = {
            "database_name": "amaris_staging_postgres",
            "database_role": "amaris_staging_postgres_user",
            "schema_name": "public",
        }
        self.assertTrue(validate_render_facts(safe))
        for key in safe:
            self.assertFalse(validate_render_facts({**safe, key: "different"}))


if __name__ == "__main__":
    unittest.main()
