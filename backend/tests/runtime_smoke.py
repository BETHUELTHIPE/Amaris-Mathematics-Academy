"""Real local Nginx/Gunicorn/Uvicorn smoke tests; never targets a remote host.

Run: python -m tests.runtime_smoke. Requires nginx and collected static assets.
All requests are synthetic and loopback-only; no emails or payment are issued.
"""

import concurrent.futures
import gzip
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from amaris_cms.web_runtime import BACKEND_DIR, render_config, stop_process


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request(port, path, *, body=None, headers=None):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=body,
        headers={"X-Forwarded-Proto": "https", **(headers or {})},
    )
    try:
        response = urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, response.headers, response.read()


def wait_ready(port, process):
    for _ in range(100):
        if process.poll() is not None:
            raise AssertionError("Runtime exited before readiness")
        try:
            if request(port, "/health/ready/")[0] == 200:
                return
        except OSError:
            pass
        time.sleep(0.1)
    raise AssertionError("Local readiness timed out")


def main():
    # Keep the subprocess isolated from any inherited production bindings.
    env = {key: value for key, value in os.environ.items() if key in {"PATH", "LD_LIBRARY_PATH", "SYSTEMROOT"}}
    env.update(
        DJANGO_DEBUG="false",
        DJANGO_SECRET_KEY="synthetic-runtime-only-key-not-used-outside-this-process",
        DJANGO_ALLOWED_HOSTS="localhost,127.0.0.1",
        SUPABASE_DATABASE_REQUIRED="false",
        DATABASE_SSL_REQUIRED="false",
        WEB_CONCURRENCY="1",
        AMARIS_COLOCATE_NOTIFICATIONS="false",
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        NGINX_TRUST_FORWARDED_PROTO="true",
    )
    for key in ("NGINX_BINARY", "NGINX_MIME_TYPES"):
        if key in os.environ:
            env[key] = os.environ[key]
    port, upstream = free_port(), free_port()
    env.update(PORT=str(port), GUNICORN_UPSTREAM_PORT=str(upstream))
    with tempfile.TemporaryDirectory(prefix="amaris-runtime-smoke-") as root:
        directory = Path(root)
        env["DATABASE_URL"] = "sqlite:///" + str(directory / "synthetic.sqlite3")
        with (directory / "django-runtime.log").open("w+") as output:
            runtime = subprocess.Popen(
                [sys.executable, "-m", "amaris_cms.web_runtime"],
                cwd=BACKEND_DIR,
                env=env,
                stdout=output,
                stderr=output,
                start_new_session=True,
            )
            try:
                wait_ready(port, runtime)
                for path in ("/media/student-private/invoice.pdf", "/media/invoice.pdf", "/metrics"):
                    assert request(port, path)[0] == 404, path
                status, headers, _body = request(port, "/static/admin/css/base.css")
                assert status == 200 and "max-age=3600" in headers.get("Cache-Control", "")
                status, headers, body = request(port, "/static/admin/css/base.css", headers={"Accept-Encoding": "gzip"})
                assert status == 200 and headers.get("Content-Encoding") == "gzip"
                assert gzip.decompress(body) == (BACKEND_DIR / "staticfiles/admin/css/base.css").read_bytes()
                assert body == (BACKEND_DIR / "staticfiles/admin/css/base.css.gz").read_bytes()
                assert request(port, "/health/version/")[0] == 200
            except Exception:
                output.seek(0)
                print(output.read())  # Only the clean synthetic environment above is used.
                raise
            finally:
                stop_process(runtime, signal.SIGTERM, 95)
            assert runtime.returncode == 0, "Paired runtime did not shut down cleanly"
            print("PASS paired Django runtime, readiness, static serving, private paths and graceful shutdown")

        # Test proxy semantics and admission control against synthetic ASGI work.
        env.update(GUNICORN_BIND=f"127.0.0.1:{upstream}", UVICORN_LIMIT_CONCURRENCY="4")
        config = render_config(directory, port, upstream)
        with (directory / "fixture.log").open("w+") as output:
            gunicorn = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "gunicorn",
                    "-c",
                    str(BACKEND_DIR / "gunicorn.conf.py"),
                    "tests.runtime_asgi_fixture:application",
                ],
                cwd=BACKEND_DIR,
                env=env,
                stdout=output,
                stderr=output,
                start_new_session=True,
            )
            proxy = None
            try:
                wait_ready(upstream, gunicorn)
                proxy = subprocess.Popen(
                    [
                        env.get("NGINX_BINARY", "nginx"),
                        "-e",
                        "stderr",
                        "-p",
                        root + "/",
                        "-c",
                        str(config),
                        "-g",
                        "daemon off;",
                    ],
                    stdout=output,
                    stderr=output,
                    start_new_session=True,
                )
                wait_ready(port, proxy)
                for user in ("synthetic-student-A", "synthetic-student-B"):
                    status, headers, body = request(port, "/private", headers={"Authorization": user})
                    assert status == 200 and json.loads(body)["authorization"] == user
                    assert headers["Cache-Control"] == "private, no-store"
                status, _headers, body = request(port, "/echo", body=b"synthetic=booking&signature=unchanged")
                assert status == 200 and json.loads(body)["body"] == "synthetic=booking&signature=unchanged"
                status, headers, _body = request(port, "/failure")
                assert status == 503 and headers["Content-Type"] == "application/json"
                started = time.monotonic()
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/stream", timeout=5) as stream:
                    assert stream.read(6) == b"first\n" and time.monotonic() - started < 0.4
                    assert stream.read() == b"last\n"
                with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
                    statuses = list(executor.map(lambda _: request(upstream, "/slow")[0], range(16)))
                assert 503 in statuses and set(statuses) <= {200, 503}, statuses
                assert request(upstream, "/health/ready/")[0] == 200
                print(
                    "PASS protected response isolation, exact POST body, JSON 503, streaming, "
                    "overload shedding and recovery"
                )
            finally:
                if proxy:
                    stop_process(proxy, signal.SIGQUIT, 30)
                stop_process(gunicorn, signal.SIGTERM, 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
