from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from amaris_cms.urls import _postgresql_available


class PostgreSQLReadinessTests(SimpleTestCase):
    @patch("amaris_cms.urls.connection")
    def test_non_postgresql_database_is_not_reported_as_postgresql(self, database):
        database.vendor = "sqlite"

        self.assertFalse(_postgresql_available())
        database.cursor.assert_not_called()

    @patch("amaris_cms.urls.connection")
    def test_postgresql_requires_a_successful_query(self, database):
        database.vendor = "postgresql"
        cursor = MagicMock()
        cursor.fetchone.return_value = (1,)
        database.cursor.return_value.__enter__.return_value = cursor

        self.assertTrue(_postgresql_available())
        cursor.execute.assert_called_once_with("SELECT 1")

    @patch("amaris_cms.urls.connection")
    def test_postgresql_query_failure_is_unavailable(self, database):
        database.vendor = "postgresql"
        database.cursor.side_effect = OSError("synthetic database outage")

        self.assertFalse(_postgresql_available())
