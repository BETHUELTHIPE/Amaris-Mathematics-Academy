from django.test import SimpleTestCase

from manage import is_approved_staging_migration_branch


class StagingMigrationBranchSafetyTests(SimpleTestCase):
    def test_original_and_pinned_recovery_branch_allowed(self):
        self.assertTrue(is_approved_staging_migration_branch("staging"))
        self.assertTrue(
            is_approved_staging_migration_branch("ops/staging-known-good-af8709c-20261019")
        )

    def test_production_main_and_unrecognized_branches_denied(self):
        for branch in (
            "main",
            "production-release-20260923",
            "render-live-current-20260918",
            "ops/staging-known-good-af8709c-20261019-extra",
            "",
            "Staging",
        ):
            with self.subTest(branch=branch):
                self.assertFalse(is_approved_staging_migration_branch(branch))
