"""Exercise actual NGINX routing against synthetic auth/console servers.

Run with: python monitoring/self-hosted/test_gateway.py
NGINX_BINARY may point at an unpacked nginx binary. No production calls are made.
"""

import http.client
import json
import os
import pwd
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from render_config import https_origin, render

HERE = Path(__file__).resolve().parent
TOKEN = "synthetic-query-token-" + "x" * 43


class MockUpstream(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/admin/monitoring/access/":
            cookie = self.headers.get("Cookie", "")
            status = {
                "session=superuser": 204,
                "session=staff": 403,
                "session=student": 403,
                "session=tutor": 403,
                "session=unavailable": 500,
            }.get(cookie, 401)
            self.send_response(status)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(
            json.dumps(
                {
                    "path": self.path,
                    "cookie": self.headers.get("Cookie"),
                    "authorization": self.headers.get("Authorization"),
                    "identity": self.headers.get("X-WEBAUTH-USER"),
                }
            ).encode()
        )

    do_POST = do_GET

    def log_message(self, *_args):
        pass


class ConfigTests(unittest.TestCase):
    def test_rejects_config_injection_and_insecure_auth_origins(self):
        for value in (
            "http://django.example",
            "https://user:pass@django.example",
            "https://django.example/a",
            "https://django.example;return 200",
            "https://django.example\n",
            "https://django.example?x=1",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                https_origin(value)


class GatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = os.getenv("NGINX_BINARY") or shutil.which("nginx")
        if not cls.binary:
            raise RuntimeError("NGINX is required to verify authorization routing.")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        (cls.root / "logs").mkdir()
        cls.mock = ThreadingHTTPServer(("127.0.0.1", 0), MockUpstream)
        cls.thread = threading.Thread(target=cls.mock.serve_forever, daemon=True)
        cls.thread.start()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            cls.port = listener.getsockname()[1]
        original = Path.read_text

        def read(path, *args, **kwargs):
            if str(path) == "/run/secrets/prometheus_api_token":
                return TOKEN
            if str(path) == "/config/gateway.conf.template":
                return original(HERE / "gateway.conf.template")
            return original(path, *args, **kwargs)

        with (
            patch.dict(os.environ, {"DJANGO_ORIGIN": "https://django.example", "MONITORING_DOMAIN": "monitor.example"}),
            patch.object(Path, "read_text", read),
        ):
            render(cls.root)
        upstream = f"127.0.0.1:{cls.mock.server_port}"
        config = (cls.root / "gateway.conf").read_text().replace("listen 8080;", f"listen {cls.port};")
        config = config.replace("https://django.example", "http://" + upstream)
        for console in ("flower:5555", "prometheus:9090", "grafana:3000", "cadvisor:8080"):
            config = config.replace(console, upstream)
        cls.config = cls.root / "nginx.conf"
        cls.config.write_text(
            f"user {pwd.getpwuid(os.getuid()).pw_name}; daemon off; master_process off; "
            f"pid {cls.root}/pid; error_log {cls.root}/error.log;\n"
            f"events {{}}\nhttp {{ access_log off; {config} }}\n"
        )
        checked = subprocess.run([cls.binary, "-t", "-p", str(cls.root), "-c", str(cls.config)], capture_output=True)
        if checked.returncode:
            raise RuntimeError(checked.stderr.decode())
        cls.process = subprocess.Popen(
            [cls.binary, "-p", str(cls.root), "-c", str(cls.config)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", cls.port), timeout=0.1):
                    return
            except OSError:
                if cls.process.poll() is not None:
                    raise RuntimeError(cls.process.stderr.read().decode()) from None
                time.sleep(0.02)
        raise RuntimeError("NGINX did not start.")

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=5)
        cls.process.stderr.close()
        cls.mock.shutdown()
        cls.mock.server_close()
        cls.tmp.cleanup()

    def request(self, path, cookie="", method="GET", headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.request(method, path, headers={"Cookie": cookie, **(headers or {})})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_every_console_and_nested_api_requires_current_superuser(self):
        for console in ("flower", "grafana", "prometheus", "cadvisor"):
            for suffix in ("/", "/api/test?x=1"):
                path = f"/monitoring/{console}{suffix}"
                for role in ("student", "tutor", "staff"):
                    with self.subTest(path=path, role=role):
                        self.assertEqual(self.request(path, "session=" + role)[0], 403)
                with self.subTest(path=path):
                    self.assertEqual(self.request(path)[0], 302)
                    self.assertEqual(self.request(path, "session=superuser")[0], 200)
                    self.assertEqual(self.request(path, "session=unavailable")[0], 500)

    def test_slashless_urls_only_redirect_to_protected_routes(self):
        for console in ("flower", "grafana", "prometheus", "cadvisor"):
            for role in ("", "session=staff", "session=superuser"):
                status, headers, body = self.request(f"/monitoring/{console}", role)
                self.assertEqual(status, 301)
                self.assertEqual(headers["Location"], f"/monitoring/{console}/")
                self.assertNotIn(b'"cookie"', body)

    def test_tools_do_not_receive_django_cookies_or_client_authorization(self):
        for console in ("flower", "grafana", "prometheus", "cadvisor"):
            with self.subTest(console=console):
                status, headers, body = self.request(
                    f"/monitoring/{console}/",
                    "session=superuser",
                    headers={"Authorization": "Bearer spoof", "X-WEBAUTH-USER": "admin"},
                )
                self.assertEqual(status, 200)
                data = json.loads(body)
                self.assertIsNone(data["cookie"])
                self.assertIsNone(data["authorization"])
                self.assertIn("no-store", headers["Cache-Control"])
                if console == "grafana":
                    self.assertEqual(data["identity"], "django-monitoring-viewer")

    def test_service_token_cannot_open_console_and_api_rejects_sessions(self):
        path = "/monitoring-api/api/v1/query?query=up"
        self.assertEqual(self.request(path, "session=superuser")[0], 401)
        self.assertEqual(self.request(path, headers={"Authorization": "Bearer wrong"})[0], 401)
        self.assertEqual(self.request(path, headers={"Authorization": "Bearer " + TOKEN})[0], 200)
        self.assertEqual(self.request("/monitoring/prometheus/", headers={"Authorization": "Bearer " + TOKEN})[0], 302)
        self.assertEqual(self.request("/monitoring-api/api/v1/admin/tsdb/delete_series")[0], 404)

    def test_readonly_tools_and_grafana_cross_origin_requests(self):
        for console in ("flower", "prometheus", "cadvisor"):
            self.assertEqual(self.request(f"/monitoring/{console}/api/test", "session=superuser", "POST")[0], 403)
        path = "/monitoring/grafana/api/ds/query"
        for headers in ({}, {"Origin": "https://attacker.example"}):
            self.assertEqual(self.request(path, "session=superuser", "POST", headers)[0], 403)
        self.assertEqual(self.request(path, "session=superuser", "POST", {"Origin": "https://monitor.example"})[0], 200)
        self.assertEqual(self.request(path, "session=staff", "POST", {"Origin": "https://monitor.example"})[0], 403)

    def test_auth_endpoint_and_unlisted_ports_paths_are_not_public(self):
        for path in ("/_monitoring_auth", "/admin/monitoring/access/", "/metrics", "/api/v1/query", "/login", "/"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path, "session=superuser")[0], 404)


if __name__ == "__main__":
    unittest.main()
