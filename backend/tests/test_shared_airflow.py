"""Shared container isolation, website continuity and shutdown checks."""

import importlib.util
import os
import signal
import ssl
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("shared_airflow", Path(__file__).parents[1] / "ops/shared_airflow/run.py")
SHARED = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARED)


class SharedAirflowTests(TestCase):
    def source(self):
        return {
            "PATH": os.environ["PATH"],
            "DATABASE_URL": "postgresql://django:test@db/app",
            "SHARED_AIRFLOW_DATABASE_URL": "postgresql://airflow:test@db/app?sslmode=require",
            "SHARED_AIRFLOW_SCHEMA": "amaris_airflow",
            "SHARED_AIRFLOW_FERNET_KEY": "test-only",
            "SHARED_AIRFLOW_JWT_SECRET": "test-only-jwt",
            "SHARED_AIRFLOW_API_SECRET": "test-only-api",
            "SUPABASE_SERVICE_ROLE_KEY": "must-never-reach-airflow",
            "PAYFAST_MERCHANT_KEY": "must-never-reach-airflow",
            "OPENAI_API_KEY": "must-never-reach-airflow",
            "PORT": "10000",
        }

    def test_airflow_environment_excludes_website_secrets_and_has_isolated_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            env, ca_file = SHARED.airflow_environment(self.source(), Path(directory))
            self.assertNotIn("DATABASE_URL", env)
            for key in ("SUPABASE_SERVICE_ROLE_KEY", "PAYFAST_MERCHANT_KEY", "OPENAI_API_KEY"):
                self.assertNotIn(key, env)
            self.assertEqual(env["AIRFLOW__DATABASE__SQL_ALCHEMY_SCHEMA"], "amaris_airflow")
            self.assertEqual(env["AMARIS_WEBSITE_READINESS_URL"], "http://127.0.0.1:10000/health/ready/")
            context = ssl.create_default_context(cafile=ca_file)
            self.assertTrue(context.check_hostname)
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            self.assertEqual(Path(env["AIRFLOW__API__SSL_KEY"]).stat().st_mode & 0o777, 0o600)

    def test_same_database_role_and_public_schema_are_rejected(self):
        source = self.source()
        source["SHARED_AIRFLOW_DATABASE_URL"] = source["DATABASE_URL"]
        with self.assertRaises(ValueError):
            SHARED.airflow_environment(source, Path("/unused"))
        source = self.source()
        for schema in ("public", "auth", "storage", "bad;sql", ""):
            with self.subTest(schema=schema), self.assertRaises(ValueError):
                SHARED.airflow_environment(dict(source, SHARED_AIRFLOW_SCHEMA=schema), Path("/unused"))

    @patch.object(SHARED, "verify_metadata_role", side_effect=ValueError("fake private connection details"))
    def test_failed_airflow_preflight_still_starts_website_without_secrets(self, verify):
        source = dict(self.source(), SHARED_AIRFLOW_ENABLED="true", AIRFLOW_MONITORING_ENABLED="true")
        web = SimpleNamespace(poll=lambda: 0, wait=lambda **kwargs: 0, returncode=0)
        with (
            patch.dict(os.environ, source, clear=True),
            patch.object(SHARED.sys, "argv", ["run.py"]),
            patch.object(SHARED.signal, "signal"),
            patch.object(SHARED.subprocess, "Popen", return_value=web) as spawn,
            patch("builtins.print") as output,
        ):
            self.assertEqual(SHARED.main(), 0)
        self.assertEqual(spawn.call_count, 1)
        passed = spawn.call_args.kwargs["env"]
        self.assertEqual(passed["AIRFLOW_MONITORING_ENABLED"], "false")
        self.assertFalse(any(key.startswith("SHARED_AIRFLOW_") for key in passed))
        self.assertNotIn("fake private connection", repr(output.call_args_list))

    def test_shutdown_signals_process_groups(self):
        child = SimpleNamespace(poll=lambda: None, pid=9999, wait=lambda **kwargs: 0)
        with patch.object(SHARED.os, "killpg") as kill:
            SHARED.stop([child])
        kill.assert_called_once_with(9999, signal.SIGTERM)

    @patch("psycopg.connect")
    def test_metadata_privilege_preflight_checks_private_search_path(self, connect):
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        for rows, valid in (
            ([(False,), (True,), ("amaris_airflow", False), (False,)], True),
            ([(True,)], False),
            ([(False,), (False,)], False),
            ([(False,), (True,), ("public", False)], False),
            ([(False,), (True,), ("amaris_airflow", True)], False),
            ([(False,), (True,), ("amaris_airflow", False), (True,)], False),
        ):
            cursor.fetchone.side_effect = rows
            with self.subTest(rows=rows):
                if valid:
                    SHARED.verify_metadata_role(self.source())
                else:
                    with self.assertRaises(ValueError):
                        SHARED.verify_metadata_role(self.source())
