"""Opt-in Django + Airflow processes inside one container, without Docker-in-Docker.

Only Django listens publicly. Airflow uses verified TLS on loopback and a
separate virtualenv, metadata role/schema and environment. No cloud resources
are provisioned, and no database migration runs automatically on web boot.
"""

import ipaddress
import os
import re
import signal
import ssl
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

AIRFLOW = "/opt/airflow-venv/bin/airflow"
ROOT = Path(__file__).resolve().parent
FAB = "airflow.providers.fab.auth_manager.fab_auth_manager.FabAuthManager"


def airflow_environment(source, directory):
    """Do not pass Django, PayFast, Supabase, email or AI credentials to Airflow."""
    database = source.get("SHARED_AIRFLOW_DATABASE_URL", "")
    parsed = urlsplit(database)
    schema = source.get("SHARED_AIRFLOW_SCHEMA", "")
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname or not parsed.username:
        raise ValueError("A separate PostgreSQL metadata credential is required")
    if unquote(parsed.username) == unquote(urlsplit(source.get("DATABASE_URL", "")).username or ""):
        raise ValueError("Airflow must not reuse the application's database role")
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"} and parse_qs(parsed.query).get("sslmode", [""])[
        0
    ] not in {"require", "verify-ca", "verify-full"}:
        raise ValueError("Off-host metadata connections must require TLS")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", schema) or schema in {"public", "auth", "storage"}:
        raise ValueError("A dedicated private metadata schema is required")
    secret_keys = ("SHARED_AIRFLOW_FERNET_KEY", "SHARED_AIRFLOW_JWT_SECRET", "SHARED_AIRFLOW_API_SECRET")
    if any(not source.get(key) for key in secret_keys):
        raise ValueError("Airflow runtime secrets are missing")
    env = {k: source[k] for k in ("PATH", "LANG", "LC_ALL", "HOME", "TZ") if k in source}
    env.update(
        {
            "AIRFLOW_HOME": "/opt/airflow",
            "AIRFLOW__CORE__DAGS_FOLDER": str(ROOT / "dags"),
            "AIRFLOW__CORE__EXECUTOR": "LocalExecutor",
            "AIRFLOW__CORE__AUTH_MANAGER": FAB,
            "AIRFLOW__CORE__LOAD_EXAMPLES": "False",
            "AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION": "True",
            "AIRFLOW__CORE__PARALLELISM": "1",
            "AIRFLOW__CORE__MAX_ACTIVE_TASKS_PER_DAG": "1",
            "AIRFLOW__CORE__MAX_ACTIVE_RUNS_PER_DAG": "1",
            "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN": re.sub(r"^postgres(?:ql)?://", "postgresql+psycopg2://", database),
            "AIRFLOW__DATABASE__SQL_ALCHEMY_SCHEMA": schema,
            "AIRFLOW__DATABASE__SQL_ALCHEMY_POOL_SIZE": "1",
            "AIRFLOW__DATABASE__SQL_ALCHEMY_MAX_OVERFLOW": "1",
            "AIRFLOW__CORE__FERNET_KEY": source["SHARED_AIRFLOW_FERNET_KEY"],
            "AIRFLOW__API_AUTH__JWT_SECRET": source["SHARED_AIRFLOW_JWT_SECRET"],
            "AIRFLOW__API__SECRET_KEY": source["SHARED_AIRFLOW_API_SECRET"],
            "AIRFLOW__CORE__EXECUTION_API_SERVER_URL": "https://localhost:8443/execution/",
            "AIRFLOW__API__BASE_URL": "https://localhost:8443",
            "AIRFLOW__METRICS__STATSD_ON": "False",
            "AIRFLOW__LOGGING__LOGGING_LEVEL": "WARNING",
            "AIRFLOW__DAG_PROCESSOR__PARSING_PROCESSES": "1",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "AMARIS_WEBSITE_READINESS_URL": "http://127.0.0.1:"
            + str(int(source.get("PORT", "8000")))
            + "/health/ready/",
        }
    )
    # Local certificate valid for this container only. No public domain needed.
    # Django/Airflow trust its CA explicitly; never turn off TLS verification.
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Amaris container-local CA")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), critical=False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    pem, private = directory / "local-ca.pem", directory / "local.key"
    pem.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    private.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    pem.chmod(0o600)
    private.chmod(0o600)
    bundle = directory / "ca-bundle.pem"
    default = ssl.get_default_verify_paths().cafile
    bundle.write_text((Path(default).read_text() if default else "") + "\n" + pem.read_text())
    bundle.chmod(0o600)
    env.update(
        {
            "AIRFLOW__API__SSL_CERT": str(pem),
            "AIRFLOW__API__SSL_KEY": str(private),
            "AIRFLOW__API__SSL_CA_FILE": str(pem),
            "SSL_CERT_FILE": str(bundle),
            "REQUESTS_CA_BUNDLE": str(bundle),
        }
    )
    return env, str(pem)


def verify_metadata_role(source):
    """Read-only check before Airflow may use/migrate an existing PostgreSQL DB."""
    import psycopg

    schema = source["SHARED_AIRFLOW_SCHEMA"]
    with psycopg.connect(source["SHARED_AIRFLOW_DATABASE_URL"], connect_timeout=5) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb "
                "FROM pg_roles WHERE rolname = current_user"
            )
            if cursor.fetchone()[0]:
                raise ValueError("Airflow metadata role is overprivileged")
            cursor.execute(
                "SELECT pg_get_userbyid(nspowner) = current_user FROM pg_namespace WHERE nspname = %s", [schema]
            )
            owned = cursor.fetchone()
            if not owned or not owned[0]:
                raise ValueError("Metadata role must own its private schema")
            cursor.execute("SELECT current_schema(), has_schema_privilege(current_user, 'public', 'CREATE')")
            current, public_create = cursor.fetchone()
            if current != schema or public_create:
                raise ValueError("Metadata role must default to its private schema and cannot create public tables")
            cursor.execute(
                """SELECT EXISTS (
                SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', %s)
                AND n.nspname NOT LIKE 'pg_%%' AND c.relkind IN ('r','p','v','m','f')
                AND has_table_privilege(current_user, c.oid, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE')
            )""",
                [schema],
            )
            if cursor.fetchone()[0]:
                raise ValueError("Metadata role can access application tables")


def stop(children):
    for child in children:
        if child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    deadline = time.monotonic() + 25
    for child in children:
        try:
            child.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()


def main():
    source = dict(os.environ)
    migrate = sys.argv[1:] == ["migrate"]
    cli = sys.argv[1:2] == ["cli"] and len(sys.argv) > 2
    if sys.argv[1:] and not migrate and not cli:
        raise SystemExit("Use migrate or cli followed by explicit Airflow CLI arguments")
    web_env = {k: v for k, v in source.items() if not k.startswith("SHARED_AIRFLOW_")}
    web_env["GUNICORN_BIND"] = "0.0.0.0:" + source.get("PORT", "8000")
    commands = []
    airflow_env = None
    directory = tempfile.TemporaryDirectory(prefix="amaris-airflow-")
    try:
        if source.get("SHARED_AIRFLOW_ENABLED", "false").lower() == "true" or migrate or cli:
            airflow_env, ca_file = airflow_environment(source, Path(directory.name))
            verify_metadata_role(source)
            if migrate:
                return subprocess.call([AIRFLOW, "db", "migrate"], env=airflow_env)
            if cli:
                return subprocess.call([AIRFLOW, *sys.argv[2:]], env=airflow_env)
            # A restart must never silently mutate an existing application's DB.
            subprocess.run(
                [AIRFLOW, "db", "check-migrations", "--migration-wait-timeout", "10"],
                env=airflow_env,
                check=True,
                timeout=30,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            web_env["AIRFLOW_API_BASE_URL"] = "https://localhost:8443"
            web_env["AIRFLOW_API_CA_CERT_FILE"] = ca_file
            commands = [
                [AIRFLOW, "api-server", "--host", "127.0.0.1", "--port", "8443", "--workers", "1"],
                [AIRFLOW, "scheduler"],
                [AIRFLOW, "dag-processor"],
            ]
    except Exception:
        # Keep the website running; no secret connection details in log errors.
        if migrate or cli:
            raise SystemExit("Airflow metadata isolation/migration preflight failed") from None
        print("Airflow unavailable: metadata isolation, runtime secrets or migrations are not ready.", flush=True)
        web_env["AIRFLOW_MONITORING_ENABLED"] = "false"
    children = []
    stopping = False

    def shutdown(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        web = subprocess.Popen(
            ["gunicorn", "amaris_cms.asgi:application", "--config", "/app/gunicorn.conf.py"],
            env=web_env,
            start_new_session=True,
        )
        children.append(web)
        for command in commands:
            children.append(subprocess.Popen(command, env=airflow_env, start_new_session=True))
        failed = set()
        while not stopping and web.poll() is None:
            for index, child in enumerate(children[1:], start=1):
                if child.poll() is not None and index not in failed:
                    failed.add(index)
                    print(
                        "An Airflow process stopped; the website stays running. "
                        "Review admin availability and container logs.",
                        flush=True,
                    )
            time.sleep(0.5)
        return web.returncode or 0
    finally:
        stop(children)
        directory.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
