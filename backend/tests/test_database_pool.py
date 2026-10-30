from copy import deepcopy
from unittest import skipUnless

from django.db import connection
from django.db.backends.postgresql.base import DatabaseWrapper
from django.test import TransactionTestCase


@skipUnless(connection.vendor == "postgresql", "Requires isolated PostgreSQL")
class DatabasePoolTests(TransactionTestCase):
    def setUp(self):
        self.config = deepcopy(connection.settings_dict)
        self.config["CONN_MAX_AGE"] = 0
        self.config["OPTIONS"]["pool"] = {"min_size": 0, "max_size": 1, "max_waiting": 1, "timeout": 0.2}
        self.db = DatabaseWrapper(self.config, alias="runtime-pool-test")

    def tearDown(self):
        self.db.close()
        self.db.close_pool()

    def test_request_close_returns_physical_connection_for_reuse(self):
        with self.db.cursor() as cursor:
            cursor.execute("SELECT pg_backend_pid()")
            original = cursor.fetchone()[0]
        self.db.close()
        with self.db.cursor() as cursor:
            cursor.execute("SELECT pg_backend_pid()")
            self.assertEqual(cursor.fetchone()[0], original)
        self.assertEqual(self.db.pool.get_stats()["pool_size"], 1)

    def test_pool_limit_does_not_open_an_extra_postgres_session(self):
        from psycopg_pool import PoolTimeout

        self.db.ensure_connection()
        with self.assertRaises(PoolTimeout):
            self.db.pool.getconn(timeout=0.05)
        self.assertEqual(self.db.pool.get_stats()["pool_size"], 1)
