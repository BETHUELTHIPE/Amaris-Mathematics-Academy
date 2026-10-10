"""Network-free regression tests for staging backup safety (never use live credentials)."""
import unittest
from datetime import datetime, timedelta, timezone

from scripts.release.check_staging_backup_readiness import (
    ReadinessError,
    validate_configuration,
    verify_recent_snapshot,
)


class StagingBackupSafetyTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "STAGING_BACKUP_DATABASE_URL": "postgresql://test:fake@staging-db.internal:5432/amaris_staging",
            "STAGING_BACKUP_EXPECTED_DB_HOST": "staging-db.internal",
            "STAGING_BACKUP_EXPECTED_DB_NAME": "amaris_staging",
            "RESTIC_REPOSITORY": "s3:https://backup.example.invalid/amaris-staging",
            "RESTIC_PASSWORD": "test-only",
            "AWS_ACCESS_KEY_ID": "test-only",
            "AWS_SECRET_ACCESS_KEY": "test-only",
        }

    def test_valid_staging_configuration(self):
        self.assertEqual(validate_configuration(self.env), 48)

    def test_rejects_missing_credentials(self):
        self.env.pop("RESTIC_PASSWORD")
        with self.assertRaises(ReadinessError):
            validate_configuration(self.env)

    def test_rejects_production_database(self):
        self.env["STAGING_BACKUP_DATABASE_URL"] = "postgresql://test:fake@production-db.internal/prod_students"
        self.env["STAGING_BACKUP_EXPECTED_DB_HOST"] = "production-db.internal"
        self.env["STAGING_BACKUP_EXPECTED_DB_NAME"] = "prod_students"
        with self.assertRaises(ReadinessError):
            validate_configuration(self.env)

    def test_rejects_host_substitution(self):
        self.env["STAGING_BACKUP_DATABASE_URL"] = "postgresql://test:fake@other.example/amaris_staging"
        with self.assertRaises(ReadinessError):
            validate_configuration(self.env)

    def test_rejects_local_repository(self):
        self.env["RESTIC_REPOSITORY"] = "/tmp/fake-restic"
        with self.assertRaises(ReadinessError):
            validate_configuration(self.env)

    def test_rejects_out_of_range_snapshot_age(self):
        self.env["STAGING_BACKUP_MAX_AGE_HOURS"] = "0"
        with self.assertRaises(ReadinessError):
            validate_configuration(self.env)

    def test_recent_tagged_backup_passes(self):
        now = datetime(2026, 10, 10, tzinfo=timezone.utc)
        snapshots = [{"time": (now - timedelta(hours=3)).isoformat(), "tags": ["automated", "amaris", "staging"]}]
        verify_recent_snapshot(snapshots, 48, now=now)

    def test_stale_snapshot_fails(self):
        now = datetime(2026, 10, 10, tzinfo=timezone.utc)
        snapshots = [{"time": (now - timedelta(hours=50)).isoformat(), "tags": ["automated", "amaris", "staging"]}]
        with self.assertRaises(ReadinessError):
            verify_recent_snapshot(snapshots, 48, now=now)

    def test_non_staging_environment_tag_fails(self):
        now = datetime(2026, 10, 10, tzinfo=timezone.utc)
        snapshots = [{"time": now.isoformat(), "tags": ["automated", "amaris", "production"]}]
        with self.assertRaises(ReadinessError):
            verify_recent_snapshot(snapshots, 48, now=now)

    def test_wrong_tag_fails(self):
        now = datetime(2026, 10, 10, tzinfo=timezone.utc)
        snapshots = [{"time": now.isoformat(), "tags": ["unrelated"]}]
        with self.assertRaises(ReadinessError):
            verify_recent_snapshot(snapshots, 48, now=now)

    def test_untrusted_snapshot_shape_fails(self):
        with self.assertRaises(ReadinessError):
            verify_recent_snapshot({}, 48)


if __name__ == "__main__":
    unittest.main()
