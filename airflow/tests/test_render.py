"""Exercise private TLS and startup ordering without touching Render or real data."""

import importlib.util
import os
import ssl
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch

import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("render_start", ROOT / "render/start.py")
START = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(START)


class RenderStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-only-private-ca")])
        now = datetime.now(UTC)
        ca = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=None,
                    decipher_only=None,
                ),
                critical=True,
            )
            .sign(key, hashes.SHA256())
        )
        server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        server = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
            .issuer_name(name)
            .public_key(server_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), critical=False)
            .sign(key, hashes.SHA256())
        )
        cls.ca = ca.public_bytes(serialization.Encoding.PEM).decode()
        cls.cert = server.public_bytes(serialization.Encoding.PEM).decode()
        cls.key = server_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ).decode()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name) / "tls"
        self.env = {
            "AIRFLOW_API_HOST": "localhost",
            "AIRFLOW__CORE__AUTH_MANAGER": "airflow.providers.fab.auth_manager.fab_auth_manager.FabAuthManager",
            "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN": "postgresql://test:test@localhost/airflow",
            "AIRFLOW__CORE__FERNET_KEY": "test-only",
            "AIRFLOW__API__SECRET_KEY": "test-only",
            "AIRFLOW__API_AUTH__JWT_SECRET": "test-only",
            "AIRFLOW_TLS_CA_PEM": self.ca,
            "AIRFLOW_TLS_CERT_PEM": self.cert,
            "AIRFLOW_TLS_KEY_PEM": self.key,
        }

    def test_private_tls_really_connects_and_rejects_wrong_hostname_and_untrusted_ca(self):
        _, context = START.configure(self.env, "api", self.directory)

        class Health(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200 if self.path == "/api/v2/monitor/health" else 404)
                self.end_headers()

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Health)
        serving = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        serving.load_cert_chain(str(self.directory / "server.pem"), str(self.directory / "server.key"))
        server.socket = serving.wrap_socket(server.socket, server_side=True)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_port
            START.wait_for_api(f"https://localhost:{port}", context, timeout=0)
            with self.assertRaises(RuntimeError):
                START.wait_for_api(f"https://127.0.0.1:{port}", context, timeout=0)
            with self.assertRaises(RuntimeError):
                START.wait_for_api(f"https://localhost:{port}", ssl.create_default_context(), timeout=0)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_worker_has_no_server_key_and_preserves_public_ca_roots(self):
        env = dict(self.env)
        START.configure(env, "scheduler", self.directory)
        self.assertFalse((self.directory / "server.key").exists())
        self.assertNotIn("AIRFLOW_TLS_KEY_PEM", env)
        self.assertNotIn("AIRFLOW__API__SSL_KEY", env)
        self.assertIn("https://localhost:8443/execution/", env.values())
        self.assertGreater((self.directory / "ca-bundle.pem").stat().st_size, len(self.ca))
        self.assertEqual((self.directory / "airflow-ca.pem").stat().st_mode & 0o777, 0o600)
        self.assertIn("postgresql+psycopg2://", env["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"])

    def test_missing_secrets_and_insecure_auth_manager_fail_closed(self):
        for key in ("AIRFLOW_TLS_CA_PEM", "AIRFLOW__CORE__FERNET_KEY", "AIRFLOW__API_AUTH__JWT_SECRET"):
            env = {k: v for k, v in self.env.items() if k != key}
            with self.subTest(key=key), self.assertRaises(ValueError):
                START.configure(env, "api", self.directory)
        env = dict(self.env, AIRFLOW__CORE__AUTH_MANAGER="SimpleAuthManager")
        with self.assertRaises(ValueError):
            START.configure(env, "api", self.directory)
        for host in ("http://localhost", "localhost:8443", "localhost/path"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                START.configure(dict(self.env, AIRFLOW_API_HOST=host), "api", self.directory)

    def test_worker_waits_without_migrating_and_execs_for_signal_delivery(self):
        with (
            patch.object(START, "configure", return_value=("https://private:8443", None)),
            patch.object(START, "wait_for_api") as health,
            patch.object(START.subprocess, "run") as run,
            patch.object(START.os, "execvpe") as execute,
            patch.dict(os.environ, self.env, clear=True),
            patch.object(START.sys, "argv", ["start.py", "scheduler"]),
        ):
            START.main()
        self.assertEqual(
            run.call_args.args[0], ["airflow", "db", "check-migrations", "--migration-wait-timeout", "180"]
        )
        health.assert_called_once_with("https://private:8443", None)
        self.assertEqual(execute.call_args.args[:2], ("airflow", ["airflow", "scheduler"]))

    def test_blueprint_keeps_database_secrets_and_api_private(self):
        blueprint = yaml.safe_load((ROOT / "render/render.yaml").read_text())
        api, scheduler, processor = blueprint["services"]
        self.assertEqual([s["type"] for s in blueprint["services"]], ["pserv", "worker", "worker"])
        self.assertEqual(blueprint["databases"][0]["ipAllowList"], [])
        self.assertNotIn("domains", api)
        self.assertIn(" migrate", api["preDeployCommand"])
        self.assertTrue(all(s["autoDeployTrigger"] == "off" for s in blueprint["services"]))
        self.assertTrue(all("preDeployCommand" not in s for s in (scheduler, processor)))
        for worker in (scheduler, processor):
            self.assertNotIn("AIRFLOW_TLS_KEY_PEM", [v.get("key") for v in worker["envVars"]])


if __name__ == "__main__":
    unittest.main()
