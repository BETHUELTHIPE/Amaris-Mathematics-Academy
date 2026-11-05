"""Local/CI Jaeger ingestion and persistence check using only synthetic data.

Usage: python monitoring/tracing/smoke.py /absolute/path/to/jaeger [--memory]
Requires the backend Python dependencies, no Docker or real application database.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

import yaml

BACKEND = Path(__file__).resolve().parents[2]
QUERY = "http://127.0.0.1:16686/admin/monitoring/jaeger/api"
OPENER = build_opener(ProxyHandler({}))


def read_json(url):
    with OPENER.open(url, timeout=1) as response:
        return json.load(response)


def wait_for(url, predicate):
    for _ in range(50):
        try:
            if predicate(read_json(url)):
                return
        except (URLError, OSError, ValueError):
            pass
        time.sleep(0.2)
    raise RuntimeError("Local Jaeger check timed out.")


def main(binary):
    with tempfile.TemporaryDirectory(prefix="amaris-jaeger-test-") as directory:
        memory = "--memory" in sys.argv
        config = BACKEND / "monitoring/tracing/jaeger.yaml"
        if memory:
            document = yaml.safe_load(config.read_text())
            document["extensions"]["jaeger_storage"]["backends"]["traces"] = {"memory": {"max_traces": 1000}}
            config = Path(directory) / "memory.yaml"
            config.write_text(yaml.safe_dump(document))
        command = [
            str(Path(binary).resolve()),
            f"--config={config}",
            "--set=extensions.jaeger_query.http.endpoint=127.0.0.1:16686",
            "--set=extensions.healthcheckv2.http.endpoint=127.0.0.1:13133",
            "--set=receivers.otlp.protocols.http.endpoint=127.0.0.1:4318",
        ]
        if not memory:
            command.extend(
                [
                    f"--set=extensions.jaeger_storage.backends.traces.badger.directories.keys={directory}/keys",
                    f"--set=extensions.jaeger_storage.backends.traces.badger.directories.values={directory}/values",
                ]
            )
        environment = {
            **os.environ,
            "DJANGO_DEBUG": "true",
            "DATABASE_URL": "sqlite:///:memory:",
            "SUPABASE_DATABASE_REQUIRED": "false",
            "OTEL_DEPLOYMENT_ENVIRONMENT": "test",
            "AMARIS_OTEL_ENABLED": "true",
            "AMARIS_OTEL_SAMPLE_RATIO": "1",
            "AMARIS_OTEL_ALLOW_INSECURE": "true",
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "http://127.0.0.1:4318/v1/traces",
            "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost",
        }
        trace_id = None
        for restart in ((False,) if memory else (False, True)):
            with open(f"{directory}/jaeger.log", "a") as log:
                process = subprocess.Popen(command, stdout=log, stderr=log)
                try:
                    wait_for(f"{QUERY}/v3/services", lambda data: "services" in data)
                    if not restart:
                        result = subprocess.run(
                            [sys.executable, "manage.py", "trace_canary"],
                            cwd=BACKEND,
                            env=environment,
                            capture_output=True,
                            text=True,
                            timeout=20,
                            check=True,
                        )
                        match = re.search(r"Synthetic trace ID: ([a-f0-9]{32})", result.stdout)
                        if match is None:
                            raise RuntimeError("Canary did not return a trace ID.")
                        trace_id = match.group(1)
                    wait_for(f"{QUERY}/traces/{trace_id}", lambda data: bool(data.get("data")))
                    if not restart:
                        # Verify the UI and static assets work at Django's proxy prefix.
                        with OPENER.open(QUERY.removesuffix("/api") + "/", timeout=2) as response:
                            if b"<html" not in response.read().lower():
                                raise RuntimeError("Jaeger UI did not return HTML.")
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
        if memory:
            print("PASS: Jaeger accepted the synthetic OTLP trace. Persistence was NOT TESTED.")
        else:
            print("PASS: Jaeger accepted the synthetic OTLP trace and retained it after restart.")


if __name__ == "__main__":
    main(sys.argv[1])
