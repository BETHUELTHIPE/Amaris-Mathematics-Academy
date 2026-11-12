"""Real whole-site Nginx routing checks against disposable Docker origins.

The default uses two synthetic replicas per application. --real-frontend replaces
the frontend fixture with the separately built production Node image. No real
accounts, email, database, payment or hosted Render resource is used.
"""

import argparse
import base64
import json
import os
import re
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "backend" / "tests" / "site_gateway"
DEPLOY = ROOT / "deploy" / "site-gateway"


def run(*args, check=True, env=None):
    result = subprocess.run(args, check=check, env=env, text=True, capture_output=True)
    return result.stdout.strip()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def inspect_manifest():
    with tempfile.TemporaryDirectory() as folder:
        envfile = Path(folder) / "synthetic.env"
        envfile.write_text("")
        env = {
            **os.environ,
            "AMARIS_BACKEND_IMAGE": "synthetic-backend:inspection",
            "AMARIS_FRONTEND_IMAGE": "synthetic-frontend:inspection",
            "AMARIS_BACKEND_ENV_FILE": str(envfile),
            "AMARIS_FRONTEND_ENV_FILE": str(envfile),
            "AMARIS_PUBLIC_ORIGIN": "https://academy.example.test",
        }
        config = json.loads(
            run("docker", "compose", "-f", str(DEPLOY / "compose.yml"), "config", "--format", "json", env=env)
        )
        services = config["services"]
        assert not services["backend"].get("ports") and not services["frontend"].get("ports")
        assert all(port["host_ip"] == "127.0.0.1" for port in services["gateway"]["ports"])
        assert services["frontend"]["environment"]["CMS_API_URL"] == "https://academy.example.test/api/v1"
        print("PASS production manifest publishes only the gateway and uses one public CMS origin", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--real-frontend", action="store_true")
    real = parser.parse_args().real_frontend
    inspect_manifest()
    project = "amaris-site-test-" + uuid.uuid4().hex[:12]
    command = ["docker", "compose", "-p", project, "-f", str(FIXTURE / "compose.yml")]
    if real:
        command.extend(["-f", str(FIXTURE / "real-frontend.yml")])

    def compose(*args, check=True):
        return run(*command, *args, check=check)

    def ids(service):
        return compose("ps", "-q", service).splitlines()

    def names(containers):
        return {run("docker", "inspect", "--format", "{{.Config.Hostname}}", item) for item in containers}

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    base = ""

    def request(path, *, body=None, headers=None):
        req = urllib.request.Request(
            base + path,
            data=body,
            headers={
                "Host": "academy.example.test",
                "X-Forwarded-Proto": "http",
                "X-Forwarded-Host": "untrusted.example.test",
                **(headers or {}),
            },
        )
        try:
            response = opener.open(req, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read()

    def distribution(path, role, expected):
        seen = set()
        deadline = time.monotonic() + 50
        healthy = 0
        while time.monotonic() < deadline:
            try:
                status, _headers, body = request(path)
                if status == 200:
                    data = json.loads(body)
                    assert data["role"] == role and data["instance"] in expected, data
                    seen.add(data["instance"])
                    healthy += 1
                    if seen == expected and healthy >= 10:
                        return
                else:
                    assert status in {502, 504}, status
                    healthy = 0
            except OSError:
                healthy = 0
            time.sleep(0.15)
        raise AssertionError(f"Discovery failed for {role}: expected={expected}, seen={seen}")

    def websocket(path, role, port):
        nonce = base64.b64encode(b"testtesttesttest").decode()
        with socket.create_connection(("127.0.0.1", port), timeout=5) as connection:
            connection.sendall(
                (
                    f"GET {path} HTTP/1.1\r\nHost: academy.example.test\r\n"
                    "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                    f"Sec-WebSocket-Version: 13\r\nSec-WebSocket-Key: {nonce}\r\n\r\n"
                ).encode()
            )
            data = b""
            while b"\r\n\r\n" not in data:
                data += connection.recv(4096)
                assert data and len(data) < 16384
            assert b" 101 " in data.split(b"\r\n", 1)[0], data
            assert f"X-Fixture-Role: {role}".lower().encode() in data.lower(), data

    def streaming(path, role):
        started = time.monotonic()
        with opener.open(base + path, timeout=5) as response:
            assert response.read(len(role) + 7) == (role + ":first\n").encode()
            assert time.monotonic() - started < 0.8
            assert response.read() == (role + ":last\n").encode()

    try:
        if real:
            compose("up", "-d")
        else:
            compose("up", "-d", "--scale", "backend=2", "--scale", "frontend=2")
        gateway = compose("ps", "-q", "gateway")
        compose("exec", "-T", "gateway", "nginx", "-t", "-c", "/etc/nginx/amaris-site.conf")
        address = compose("port", "gateway", "8080")
        assert address.startswith("127.0.0.1:"), address
        base = "http://" + address
        port = int(address.rsplit(":", 1)[1])
        if not real:
            distribution("/api/v1/identity", "backend", names(ids("backend")))

        if real:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                try:
                    if request("/health/ready/")[0] == 200 and request("/")[0] == 200:
                        break
                except OSError:
                    pass
                time.sleep(0.5)
            else:
                raise AssertionError("Actual applications did not become ready")
            for path in ("/", "/about", "/login", "/tutor/apply/login"):
                status, _headers, body = request(path)
                assert status == 200 and b"Amaris" in body, (path, status)
            status, _headers, homepage = request("/")
            assets = re.findall(r'<script[^>]+src="([^"]+)"', homepage.decode())
            asset = next(path for path in assets if path.startswith("/_next/"))
            assert request(asset)[0] == 200
            status, headers, _body = request("/dashboard")
            assert status in {302, 303, 307, 308} and "/login" in headers.get("Location", ""), (status, dict(headers))
            assert request("/api/auth-state")[0] == 200
            status, _headers, body = request("/api/v1/courses/")
            assert status == 200 and isinstance(json.loads(body)["results"], list)
            status, headers, body = request("/admin/login/")
            assert status == 200 and b"csrfmiddlewaretoken" in body
            assert "Secure" in headers.get("Set-Cookie", "")
            status, headers, body = request("/static/admin/css/base.css")
            assert status == 200 and "text/css" in headers["Content-Type"] and body
            assert request("/api/v1/student/courses/")[0] in {401, 403}
            print("PASS actual Django API, Admin login/CSRF, CSS and anonymous student denial", flush=True)
            print(
                "PASS actual Node frontend SSR, JS asset, frontend API, protected redirect and backend dispatch",
                flush=True,
            )
            return

        distribution("/identity", "frontend", names(ids("frontend")))
        backend_paths = [
            "/api/v1",
            "/api/v1/courses/?page=2",
            "/api/v1/student/courses/",
            "/api/v1/marketing-media/example/",
            "/api/schema/",
            "/api/docs/",
            "/admin",
            "/admin/login/?next=%2Fadmin%2F",
            "/admin/monitoring/",
            "/static/admin/css/base.css",
            "/health/ready/",
            "/ws/identity",
        ]
        frontend_paths = [
            "/",
            "/about",
            "/courses/example",
            "/login",
            "/auth/callback?code=synthetic",
            "/dashboard",
            "/documents/invoice",
            "/tutor/apply",
            "/api/auth-state",
            "/api/tutor-applications",
            "/api/video-requests/checkout",
            "/api/subscriptions/SUB-EXAMPLE/invoice",
            "/api/assistant",
            "/_next/static/example.js",
            "/_vinext/image?url=%2Fhero.webp",
            "/errors/404",
            "/api/v10/example",
            "/administrator",
            "/staticish",
        ]
        for role, paths in (("backend", backend_paths), ("frontend", frontend_paths)):
            for path in paths:
                status, headers, body = request(
                    path, headers={"Authorization": "synthetic-student", "Cookie": "synthetic=student"}
                )
                data = json.loads(body)
                assert status == 200 and data["role"] == role and data["path"] == path, (path, status, data)
                assert data["authorization"] == "synthetic-student" and data["cookie"] == "synthetic=student"
                assert data["host"] == data["forwarded_host"] == "academy.example.test"
                assert data["scheme"] == "https" and headers["Cache-Control"] == "private, no-store"
                assert "Secure" in headers["Set-Cookie"] and "HttpOnly" in headers["Set-Cookie"]
        print(
            "PASS frontend/backend route boundaries, query strings, cookies, authorization and HTTPS forwarding",
            flush=True,
        )

        for path in ("/media", "/media/student-private/invoice.pdf", "/metrics", "/metrics/", "/monitoring/grafana/"):
            assert request(path)[0] == 404, path
        assert request("/nginx-health/live/")[0] == 200
        payload = b"--boundary\r\nfile=synthetic\x00\x89PNG\xff\r\n--boundary--"
        for path, role in (("/api/v1/uploads/", "backend"), ("/api/tutor-applications", "frontend")):
            status, _headers, body = request(path, body=payload)
            data = json.loads(body)
            assert status == 200 and data["role"] == role
            assert base64.b64decode(data["body_b64"]) == payload
        for service, path in (("backend", "/api/v1/payfast/itn/"), ("frontend", "/api/auth-state/write-failure")):
            status, _headers, _body = request(path, body=b"synthetic=write&signature=unchanged")
            assert status == 502, status
            events = []
            for item in ids(service):
                events.extend(
                    json.loads(line)
                    for line in run("docker", "exec", item, "cat", "/tmp/site-writes.jsonl").splitlines()
                )
            assert len(events) == 1 and events[0]["role"] == service, events
        print("PASS private-file denial, byte-exact frontend/backend uploads and no POST replay", flush=True)

        streaming("/stream", "frontend")
        streaming("/api/v1/stream", "backend")
        websocket("/socket", "frontend", port)
        websocket("/ws/socket", "backend", port)
        print("PASS streaming and WebSocket upgrades for both application upstreams", flush=True)

        for service, path in (("frontend", "/identity"), ("backend", "/api/v1/identity")):
            victim, survivor = ids(service)
            run("docker", "stop", "--time", "2", victim)
            distribution(path, service, names([survivor]))
            run("docker", "rm", victim)
            compose("up", "-d", "--scale", service + "=2", "--no-recreate", service)
            distribution(path, service, names(ids(service)))
            assert compose("ps", "-q", "gateway") == gateway
        print("PASS load balancing and replacement discovery in both pools without gateway restart", flush=True)
    except Exception:
        print(compose("logs", "--no-color", "--tail", "80", check=False))
        raise
    finally:
        print(compose("down", "--volumes", "--remove-orphans", check=False))


if __name__ == "__main__":
    main()
