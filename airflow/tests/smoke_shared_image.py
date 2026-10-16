"""Measure real shared-container boot under a 2 GB cgroup; fake database only."""

import json
import os
import ssl
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib import request

from cryptography.fernet import Fernet

IMAGE = "amaris-shared-airflow:test"
NAME = "amaris-shared-ci"
PG = "amaris-shared-postgres-ci"
SCRIPT = "/app/ops/shared_airflow/run.py"


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
    env = dict(
        os.environ,
        SHARED_AIRFLOW_ENABLED="true",
        SHARED_AIRFLOW_SCHEMA="amaris_airflow",
        SHARED_AIRFLOW_DATABASE_URL="postgresql://airflow_ci:ci-only-password@localhost:5433/amaris",
        SHARED_AIRFLOW_FERNET_KEY=Fernet.generate_key().decode(),
        SHARED_AIRFLOW_JWT_SECRET="ci-only-jwt",
        SHARED_AIRFLOW_API_SECRET="ci-only-api",
        DATABASE_URL="postgresql://django_ci:ci-only-password@localhost:5433/amaris",
        DJANGO_DEBUG="false",
        DJANGO_SECRET_KEY="ci-only-django-secret-value",
        DATABASE_SSL_REQUIRED="false",
        DJANGO_ALLOWED_HOSTS="localhost,127.0.0.1",
        PORT="10000",
        WEB_CONCURRENCY="1",
        SERVICE_ROLE="ci",
    )
    flags = [
        item
        for k in env
        if k.startswith(("SHARED_AIRFLOW_", "DJANGO_", "DATABASE_")) or k in {"PORT", "WEB_CONCURRENCY", "SERVICE_ROLE"}
        for item in ("-e", k)
    ]
    try:
        docker(
            "run",
            "-d",
            "--name",
            PG,
            "-p",
            "5433:5432",
            "-e",
            "POSTGRES_PASSWORD=ci-only-password",
            "-e",
            "POSTGRES_DB=amaris",
            "postgres:17-alpine",
        )
        until(lambda: docker("exec", PG, "pg_isready", "-U", "postgres", stdout=subprocess.DEVNULL))
        docker(
            "exec",
            "-i",
            PG,
            "psql",
            "-U",
            "postgres",
            "-d",
            "amaris",
            "-v",
            "ON_ERROR_STOP=1",
            input="""
            REVOKE CREATE ON SCHEMA public FROM PUBLIC;
            CREATE ROLE django_ci LOGIN PASSWORD 'ci-only-password';
            CREATE TABLE public.synthetic_student (id integer);
            GRANT SELECT ON public.synthetic_student TO django_ci;
            CREATE ROLE airflow_ci LOGIN PASSWORD 'ci-only-password';
            CREATE SCHEMA amaris_airflow AUTHORIZATION airflow_ci;
            ALTER ROLE airflow_ci IN DATABASE amaris SET search_path = amaris_airflow, pg_catalog;
        """,
        )
        docker("run", "--rm", "--network", "host", *flags, IMAGE, "python", SCRIPT, "migrate", env=env)
        # All four processes share ONE cgroup and ONE existing-size allocation.
        docker(
            "run",
            "-d",
            "--name",
            NAME,
            "--network",
            "host",
            "--memory",
            "2g",
            "--memory-swap",
            "2g",
            *flags,
            IMAGE,
            env=env,
        )

        def website():
            req = request.Request("http://localhost:10000/health/ready/", headers={"X-Forwarded-Proto": "https"})
            with request.urlopen(req, timeout=15) as response:
                assert response.status == 200

        until(website)
        with tempfile.TemporaryDirectory() as directory:
            ca = Path(directory) / "ca.pem"

            def certificate():
                result = docker(
                    "exec",
                    NAME,
                    "python",
                    "-c",
                    "from pathlib import Path; "
                    "p=next(Path('/tmp').glob('amaris-airflow-*/local-ca.pem')); print(p.read_text())",
                    capture_output=True,
                )
                ca.write_text(result.stdout)

            until(certificate)
            context = ssl.create_default_context(cafile=str(ca))

            def api(path, token=None, data=None):
                headers = {"Content-Type": "application/json"}
                if token:
                    headers["Authorization"] = "Bearer " + token
                req = request.Request(
                    "https://localhost:8443" + path,
                    headers=headers,
                    data=json.dumps(data).encode() if data is not None else None,
                )
                with request.urlopen(req, context=context, timeout=15) as response:
                    return json.load(response)

            until(lambda: api("/api/v2/monitor/health"))
            docker(
                "exec",
                NAME,
                "python",
                SCRIPT,
                "cli",
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
                "ci-only-password",
            )
            token = api("/auth/token", data={"username": "ci-viewer", "password": "ci-only-password"})["access_token"]
            until(lambda: api("/api/v2/dags/amaris_service_health", token))
            docker("exec", NAME, "python", SCRIPT, "cli", "dags", "unpause", "amaris_service_health")

            def completed():
                runs = api("/api/v2/dags/amaris_service_health/dagRuns?limit=10", token)["dag_runs"]
                assert any(r["state"] == "success" for r in runs)

            until(completed, timeout=240)
            with ThreadPoolExecutor(max_workers=5) as pool:
                list(pool.map(lambda _: website(), range(30)))
            result = docker(
                "exec",
                PG,
                "psql",
                "-U",
                "postgres",
                "-d",
                "amaris",
                "-Atc",
                "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename <> 'synthetic_student'",
                capture_output=True,
            )
            assert result.stdout.strip() == "0", "Airflow or FAB created tables outside the private schema"
            memory = docker(
                "exec",
                NAME,
                "python",
                "-c",
                "from pathlib import Path; print(Path('/sys/fs/cgroup/memory.peak').read_text())",
                capture_output=True,
            )
            peak = int(memory.stdout.strip())
            inspect = docker("inspect", NAME, "--format", "{{.State.OOMKilled}}", capture_output=True)
            assert inspect.stdout.strip() == "false", "Combined container was OOM killed"
            assert peak < 2 * 1024**3
            Path("artifacts/shared-airflow").mkdir(parents=True, exist_ok=True)
            Path("artifacts/shared-airflow/memory.json").write_text(
                json.dumps(
                    {
                        "limit_bytes": 2 * 1024**3,
                        "peak_bytes": peak,
                        "django_workers": 1,
                        "simultaneous_airflow_tasks": 1,
                        "synthetic_readiness_requests": 30,
                        "production_capacity_verified": False,
                    },
                    indent=2,
                )
            )
            print(
                "PASS shared Docker image, isolated metadata/FAB schema, successful DAG, website readiness. "
                f"Peak: {peak} bytes."
            )
        docker("stop", "--time", "35", NAME)
        result = docker("inspect", NAME, "--format", "{{.State.ExitCode}}", capture_output=True)
        assert result.stdout.strip() == "0", "Container did not stop cleanly"
    except Exception:
        subprocess.run(["docker", "logs", "--tail", "70", NAME], check=False)
        raise
    finally:
        subprocess.run(["docker", "rm", "-f", NAME, PG], check=False, stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
