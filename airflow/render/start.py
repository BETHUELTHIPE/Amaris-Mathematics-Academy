"""Render process adapter. Never prints secret values or disables TLS checks."""

import os
import re
import ssl
import subprocess
import sys
import time
from pathlib import Path
from urllib import request


def required(env, key):
    value = env.get(key, "").strip()
    if not value or value.startswith("REPLACE_"):
        raise ValueError(f"Required setting is missing: {key}")
    return value


def configure(env, role, directory):
    """Build runtime settings before importing Airflow; mutate only our env copy."""
    if role not in {"api", "scheduler", "dag-processor", "migrate"}:
        raise ValueError("Unsupported Airflow process")
    if required(env, "AIRFLOW__CORE__AUTH_MANAGER") != (
        "airflow.providers.fab.auth_manager.fab_auth_manager.FabAuthManager"
    ):
        raise ValueError("Render requires the FAB role-based auth manager")
    host = required(env, "AIRFLOW_API_HOST")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", host):
        raise ValueError("AIRFLOW_API_HOST must be a hostname without scheme, path or port")
    for key in (
        "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN",
        "AIRFLOW__CORE__FERNET_KEY",
        "AIRFLOW__API__SECRET_KEY",
        "AIRFLOW__API_AUTH__JWT_SECRET",
    ):
        required(env, key)
    connection = env["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"].replace("postgres://", "postgresql://", 1)
    if not connection.startswith("postgresql://"):
        raise ValueError("A dedicated Render PostgreSQL connection is required")
    # Use the psycopg2 driver shipped by the constrained Airflow image.
    env["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"] = connection.replace("postgresql://", "postgresql+psycopg2://", 1)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    ca = directory / "airflow-ca.pem"
    ca.write_text(required(env, "AIRFLOW_TLS_CA_PEM") + "\n")
    ca.chmod(0o600)
    # Validate PEM contents, retain normal certificate and hostname verification.
    context = ssl.create_default_context(cafile=str(ca))
    bundle = directory / "ca-bundle.pem"
    defaults = ssl.get_default_verify_paths()
    public_roots = Path(defaults.cafile).read_text() if defaults.cafile else ""
    bundle.write_text(public_roots + "\n" + ca.read_text())
    bundle.chmod(0o600)
    env["SSL_CERT_FILE"] = str(bundle)
    env["REQUESTS_CA_BUNDLE"] = str(bundle)
    env["AIRFLOW__API__SSL_CA_FILE"] = str(ca)
    base = f"https://{host}:8443"
    env["AIRFLOW__CORE__EXECUTION_API_SERVER_URL"] = base + "/execution/"
    env["AIRFLOW__API__BASE_URL"] = base
    if role == "api":
        cert, key = directory / "server.pem", directory / "server.key"
        cert.write_text(required(env, "AIRFLOW_TLS_CERT_PEM") + "\n")
        key.write_text(required(env, "AIRFLOW_TLS_KEY_PEM") + "\n")
        cert.chmod(0o600)
        key.chmod(0o600)
        context.load_cert_chain(str(cert), str(key))
        env["AIRFLOW__API__SSL_CERT"] = str(cert)
        env["AIRFLOW__API__SSL_KEY"] = str(key)
    # Secrets passed via managed runtime env; no copied private key on workers.
    for name in ("AIRFLOW_TLS_CA_PEM", "AIRFLOW_TLS_CERT_PEM", "AIRFLOW_TLS_KEY_PEM"):
        env.pop(name, None)
    return base, context


def wait_for_api(base, context, timeout=180):
    deadline = time.monotonic() + timeout

    # Health checks never forward credentials or follow redirects.
    class NoRedirect(request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = request.build_opener(request.HTTPSHandler(context=context), NoRedirect())
    while True:
        try:
            with opener.open(base + "/api/v2/monitor/health", timeout=5) as response:
                if response.status == 200:
                    return
        except (OSError, ValueError):
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError("Airflow API did not become reachable over verified TLS")
        time.sleep(3)


def main():
    role = sys.argv[1] if len(sys.argv) == 2 else ""
    env = dict(os.environ)
    try:
        base, context = configure(env, role, Path("/tmp/amaris-airflow-tls"))
        if role == "migrate":
            # Only the API pre-deploy process owns metadata migrations.
            command = ["airflow", "db", "migrate"]
        else:
            subprocess.run(
                ["airflow", "db", "check-migrations", "--migration-wait-timeout", "180"], env=env, check=True
            )
            if role != "api":
                wait_for_api(base, context)
            command = (
                ["airflow", "api-server", "--host", "0.0.0.0", "--port", "8443", "--workers", "1"]
                if role == "api"
                else ["airflow", role]
            )
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError):
        # Exceptions from TLS/DB libraries may include credentials; redact here.
        raise SystemExit(
            "Airflow startup failed. Check required secrets, certificates, database migration and API health."
        ) from None
    os.execvpe(command[0], command, env)


if __name__ == "__main__":
    main()
