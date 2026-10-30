"""Run Nginx and Gunicorn/Uvicorn in one unprivileged managed-host container.

Gunicorn retains ownership of its existing notification supervisor. If either
web process dies, exit so the hosting platform can restart the whole workload.
"""

import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
log = logging.getLogger("amaris.web")


def port_number(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if not 1024 <= value <= 65535:
        raise ValueError(f"{name} must be an unprivileged TCP port (1024-65535).")
    return value


def render_config(directory: Path, port: int, upstream_port: int) -> Path:
    if port == upstream_port:
        raise ValueError("Nginx and Gunicorn must use different ports.")
    # Trust HTTPS forwarding only on the explicitly selected trusted-edge path.
    trust_https = os.getenv("NGINX_TRUST_FORWARDED_PROTO", os.getenv("RENDER", "false")) == "true"
    template = (BACKEND_DIR / "nginx" / "web.conf.template").read_text()
    config = template.replace("@@PORT@@", str(port)).replace("@@UPSTREAM_PORT@@", str(upstream_port))
    config = config.replace("@@STATIC_ROOT@@", json.dumps(str(BACKEND_DIR / "staticfiles") + "/"))
    config = config.replace("@@MIME_TYPES@@", json.dumps(os.getenv("NGINX_MIME_TYPES", "/etc/nginx/mime.types")))
    config = config.replace("@@TRUST_HTTPS@@", '"https" https;' if trust_https else "")
    path = directory / "nginx.conf"
    path.write_text(config)
    return path


def stop_process(child: subprocess.Popen, sig: signal.Signals, timeout: int) -> None:
    if child.poll() is not None:
        return
    try:
        child.send_signal(sig)
        child.wait(timeout=timeout)
    except ProcessLookupError:
        pass
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=5)


def serve(directory: Path, shutdown: threading.Event) -> int:
    port = port_number("PORT", 8000)
    upstream_port = port_number("GUNICORN_UPSTREAM_PORT", 8001)
    config = render_config(directory, port, upstream_port)
    nginx = [os.getenv("NGINX_BINARY", "nginx"), "-e", "stderr", "-p", str(directory) + "/", "-c", str(config)]
    subprocess.run([*nginx, "-t"], check=True)
    env = {**os.environ, "GUNICORN_BIND": f"127.0.0.1:{upstream_port}"}
    children: list[subprocess.Popen] = []
    try:
        gunicorn = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "gunicorn",
                "-c",
                str(BACKEND_DIR / "gunicorn.conf.py"),
                "amaris_cms.asgi:application",
            ],
            cwd=BACKEND_DIR,
            env=env,
            start_new_session=True,
        )
        children.append(gunicorn)
        proxy = subprocess.Popen([*nginx, "-g", "daemon off;"], start_new_session=True)
        children.append(proxy)
        log.info("Nginx reverse proxy and Gunicorn ASGI manager started")
        while not shutdown.wait(0.25):
            if any(child.poll() is not None for child in children):
                log.error("A web process exited; stopping the paired runtime")
                return 1
        return 0
    finally:
        # Stop accepting traffic and drain the proxy before terminating ASGI.
        if len(children) == 2:
            stop_process(children[1], signal.SIGQUIT, 30)
        if children:
            stop_process(children[0], signal.SIGTERM, 60)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    shutdown = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_args: shutdown.set())
    with tempfile.TemporaryDirectory(prefix="amaris-web-") as directory:
        return serve(Path(directory), shutdown)


if __name__ == "__main__":
    raise SystemExit(main())
