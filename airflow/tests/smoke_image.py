"""Boot the actual Render image against disposable CI PostgreSQL and fake sites."""

import json
import os
import ssl
import subprocess
import tempfile
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from urllib import error, request

import yaml
from cryptography.fernet import Fernet
from test_render import RenderStartupTests

IMAGE = "amaris-airflow-render:test"
PREFIX = "amaris-airflow-ci-"
NAMES = [PREFIX + role for role in ("api", "scheduler", "dag-processor", "postgres")]


def docker(*args, **kwargs):
    return subprocess.run(["docker", *args], check=True, text=True, **kwargs)


def until(operation, timeout=180):
    deadline = time.monotonic() + timeout
    while True:
        try:
            return operation()
        except (AssertionError, OSError, ValueError, subprocess.CalledProcessError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(3)


def main():
    RenderStartupTests.setUpClass()
    blueprint = yaml.safe_load((Path(__file__).resolve().parents[1] / "render/render.yaml").read_text())
    env = dict(os.environ)
    env.update({v["key"]: v.get("value", "ci-only-shared-secret") for v in blueprint["envVarGroups"][0]["envVars"]})
    env.update(
        {
            "AIRFLOW_API_HOST": "localhost",
            "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN": "postgresql://airflow:ci-only-password@localhost:5433/airflow",
            "AIRFLOW__CORE__FERNET_KEY": Fernet.generate_key().decode(),
            "AIRFLOW_TLS_CA_PEM": RenderStartupTests.ca,
            "AIRFLOW_TLS_CERT_PEM": RenderStartupTests.cert,
            "AIRFLOW_TLS_KEY_PEM": RenderStartupTests.key,
            # The health DAG must only hit the disposable fake sites in this test.
            "AMARIS_BACKEND_PUBLIC_URL": "http://localhost:8765",
            "AMARIS_STUDENT_PUBLIC_URL": "http://localhost:8765",
        }
    )
    keys = [k for k in env if k.startswith(("AIRFLOW", "AMARIS_"))]

    def run_image(name, role, detached=False):
        allowed = [k for k in keys if role == "api" or k not in {"AIRFLOW_TLS_CERT_PEM", "AIRFLOW_TLS_KEY_PEM"}]
        flags = [item for k in allowed for item in ("-e", k)]
        return docker(
            "run",
            *(["-d"] if detached else ["--rm"]),
            "--network",
            "host",
            "--name",
            name,
            *flags,
            IMAGE,
            "python",
            "/opt/airflow/render/start.py",
            role,
            env=env,
        )

    class FakeSite(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ready"}')

        def log_message(self, *args):
            pass

    fake = HTTPServer(("127.0.0.1", 8765), FakeSite)
    thread = Thread(target=fake.serve_forever, daemon=True)
    thread.start()
    try:
        docker(
            "run",
            "-d",
            "--name",
            PREFIX + "postgres",
            "-p",
            "5433:5432",
            "-e",
            "POSTGRES_USER=airflow",
            "-e",
            "POSTGRES_DB=airflow",
            "-e",
            "POSTGRES_PASSWORD=ci-only-password",
            "postgres:17-alpine",
        )
        until(lambda: docker("exec", PREFIX + "postgres", "pg_isready", "-U", "airflow", stdout=subprocess.DEVNULL))
        run_image(PREFIX + "migrate", "migrate")
        run_image(PREFIX + "api", "api", detached=True)
        with tempfile.TemporaryDirectory() as directory:
            ca = Path(directory) / "ca.pem"
            ca.write_text(RenderStartupTests.ca)
            context = ssl.create_default_context(cafile=str(ca))

            def api(path, token=None, data=None, method=None):
                headers = {"Content-Type": "application/json"}
                if token:
                    headers["Authorization"] = "Bearer " + token
                req = request.Request(
                    "https://localhost:8443" + path,
                    headers=headers,
                    data=json.dumps(data).encode() if data is not None else None,
                    method=method,
                )
                with request.urlopen(req, context=context, timeout=10) as response:
                    return json.load(response)

            until(lambda: api("/api/v2/monitor/health"))
            try:
                api("/api/v2/dags")
                raise AssertionError("Anonymous DAG access must be denied")
            except error.HTTPError as exc:
                assert exc.code in (401, 403)
            docker(
                "exec",
                PREFIX + "api",
                "airflow",
                "users",
                "create",
                "--username",
                "ci-viewer",
                "--firstname",
                "CI",
                "--lastname",
                "Viewer",
                "--role",
                "Viewer",
                "--email",
                "ci@example.invalid",
                "--password",
                "ci-only-viewer-password",
            )
            token = api("/auth/token", data={"username": "ci-viewer", "password": "ci-only-viewer-password"})[
                "access_token"
            ]
            api("/api/v2/dags", token)
            # These processes must start without receiving the API's private key.
            run_image(PREFIX + "scheduler", "scheduler", detached=True)
            run_image(PREFIX + "dag-processor", "dag-processor", detached=True)

            def imported():
                payload = api("/api/v2/dags/amaris_service_health", token)
                assert payload["dag_id"] == "amaris_service_health"
                return payload

            until(imported)
            try:
                api("/api/v2/dags/amaris_service_health/dagRuns", token, {}, "POST")
                raise AssertionError("Viewer must not be able to trigger a DAG")
            except error.HTTPError as exc:
                assert exc.code == 403
            docker("exec", PREFIX + "api", "airflow", "dags", "unpause", "amaris_service_health")

            def completed():
                runs = api("/api/v2/dags/amaris_service_health/dagRuns?limit=10", token)["dag_runs"]
                assert any(run["state"] == "success" for run in runs), "No successful synthetic health DAG run yet"

            until(completed, timeout=240)
            print(
                "PASS fresh metadata/FAB migration, verified TLS, anonymous denial, "
                "Viewer read-only, both workers, real synthetic DAG execution"
            )
    except Exception:
        for name in NAMES[:-1]:
            subprocess.run(["docker", "logs", "--tail", "50", name], check=False)
        raise
    finally:
        subprocess.run(["docker", "rm", "-f", *NAMES], check=False, stdout=subprocess.DEVNULL)
        fake.shutdown()
        fake.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    main()
