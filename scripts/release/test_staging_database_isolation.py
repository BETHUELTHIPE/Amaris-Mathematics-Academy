"""Offline release-gate tests; never connect to a real database."""

import unittest

from verify_staging_database_isolation import validate_facts


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
        self.assertFalse(validate_facts({**self.safe, "search_path": "public, amaris_staging"})[0])

    def test_any_public_write_privilege_is_rejected(self):
        self.assertFalse(validate_facts({**self.safe, "public_writable_tables": 1})[0])
        self.assertFalse(validate_facts({**self.safe, "public_schema_creatable": True})[0])

    def test_public_read_access_is_rejected(self):
        self.assertFalse(validate_facts({**self.safe, "public_readable_tables": 1})[0])

    def test_missing_or_unwritable_staging_schema_is_rejected(self):
        self.assertFalse(validate_facts({**self.safe, "staging_schema_exists": False})[0])
        self.assertFalse(validate_facts({**self.safe, "staging_schema_creatable": False})[0])


if __name__ == "__main__":
    unittest.main()
