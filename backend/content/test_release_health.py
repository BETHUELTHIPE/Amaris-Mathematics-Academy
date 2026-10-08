"""Safety tests for the OIDC-only staging database release gate."""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from content.release_health import StagingSchemaReadinessView


class StagingSchemaReadinessTests(SimpleTestCase):
    def make_request(self, provider="github-actions-oidc"):
        request = APIRequestFactory().get("/api/v1/student/acceptance/schema/")
        force_authenticate(
            request,
            user=SimpleNamespace(is_authenticated=True),
            token={"provider": provider},
        )
        return request

    @patch.dict(os.environ, {"ACCEPTANCE_GITHUB_OIDC_ENABLED": "true"})
    @patch("content.release_health.MigrationExecutor")
    @patch("content.release_health.connection")
    def test_postgresql_with_no_pending_migrations_passes(self, database, executor):
        database.vendor = "postgresql"
        cursor = database.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (1,)
        executor.return_value.loader.graph.leaf_nodes.return_value = [("content", "0001")]
        executor.return_value.migration_plan.return_value = []

        response = StagingSchemaReadinessView.as_view()(self.make_request())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {"status": "ready", "database": "postgresql", "pending_migrations": 0},
        )

    @patch.dict(os.environ, {"ACCEPTANCE_GITHUB_OIDC_ENABLED": "true"})
    @patch("content.release_health.MigrationExecutor")
    @patch("content.release_health.connection")
    def test_pending_migration_fails_closed(self, database, executor):
        database.vendor = "postgresql"
        database.cursor.return_value.__enter__.return_value.fetchone.return_value = (1,)
        executor.return_value.loader.graph.leaf_nodes.return_value = [("content", "0002")]
        executor.return_value.migration_plan.return_value = [object()]

        response = StagingSchemaReadinessView.as_view()(self.make_request())

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["pending_migrations"], 1)

    @patch.dict(os.environ, {"ACCEPTANCE_GITHUB_OIDC_ENABLED": "true"})
    @patch("content.release_health.connection")
    def test_sqlite_or_wrong_database_backend_is_rejected(self, database):
        database.vendor = "sqlite"
        response = StagingSchemaReadinessView.as_view()(self.make_request())
        self.assertEqual(response.status_code, 503)

    @patch.dict(os.environ, {"ACCEPTANCE_GITHUB_OIDC_ENABLED": "true"})
    @patch("content.release_health.connection")
    def test_database_exception_does_not_leak_details(self, database):
        database.vendor = "postgresql"
        database.cursor.side_effect = RuntimeError("secret internal connection string")
        response = StagingSchemaReadinessView.as_view()(self.make_request())
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("secret", str(response.data))

    @patch.dict(os.environ, {"ACCEPTANCE_GITHUB_OIDC_ENABLED": "true"})
    def test_non_oidc_student_is_denied(self):
        response = StagingSchemaReadinessView.as_view()(
            self.make_request(provider="supabase")
        )
        self.assertEqual(response.status_code, 403)

    @patch.dict(os.environ, {"ACCEPTANCE_GITHUB_OIDC_ENABLED": "false"})
    def test_endpoint_disabled_outside_acceptance_environment(self):
        response = StagingSchemaReadinessView.as_view()(self.make_request())
        self.assertEqual(response.status_code, 403)
