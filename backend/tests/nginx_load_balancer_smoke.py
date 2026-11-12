"""Exercise the committed Compose proxy against disposable local HTTP replicas.

Run from the repository root: python backend/tests/nginx_load_balancer_smoke.py
Requires a disposable local Docker daemon and Docker Compose v2. No real service,
database, email or payment is contacted. The native Render service is not changed.
"""

import json
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMPOSE_FILE = ROOT / "nginx_lb" / "compose.yml"


def run(*args, check=True):
    result = subprocess.run(args, check=check, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return result.stdout.strip()


def main():
    project = "amaris-lb-test-" + uuid.uuid4().hex[:12]

    def compose(*args, check=True):
        return run("docker", "compose", "-p", project, "-f", str(COMPOSE_FILE), *args, check=check)

    def instances():
        return compose("ps", "-q", "web").splitlines()

    def identities(ids):
        return {run("docker", "inspect", "--format", "{{.Config.Hostname}}", item) for item in ids}

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    base = ""

    def request(path, *, body=None, authorization=""):
        req = urllib.request.Request(base + path, data=body, headers={"Authorization": authorization})
        try:
            response = opener.open(req, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read()

    def observe(expected):
        seen = set()
        healthy = 0
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            try:
                status, _headers, body = request("/identity")
                if status == 200:
                    identity = json.loads(body)["instance"]
                    assert identity in expected, (identity, expected)
                    seen.add(identity)
                    healthy += 1
                    if seen == expected and healthy >= 12:
                        return
                else:
                    assert status in {502, 504}, status
                    healthy = 0
            except OSError:
                healthy = 0
            time.sleep(0.15)
        raise AssertionError(f"Replica discovery did not settle: expected={expected}, seen={seen}")

    try:
        compose("up", "-d", "--scale", "web=2")
        proxy = compose("ps", "-q", "nginx")
        assert proxy
        compose("exec", "-T", "nginx", "nginx", "-t")
        address = compose("port", "nginx", "80")
        assert address.startswith("127.0.0.1:"), address
        base = "http://" + address
        original = instances()
        assert len(original) == 2, original
        observe(identities(original))
        print("PASS real Nginx distributes requests to two distinct backend replicas", flush=True)

        for user in ("synthetic-student-A", "synthetic-student-B", "synthetic-student-A"):
            status, headers, body = request("/private", authorization=user)
            assert status == 200 and json.loads(body)["authorization"] == user
            assert headers["Cache-Control"] == "private, no-store"
        for path in ("/media/student-private/invoice.pdf", "/media/videos/lesson.mp4", "/metrics"):
            assert request(path)[0] == 404, path
        payload = b"synthetic=booking&signature=unchanged"
        status, _headers, body = request("/echo", body=payload)
        assert status == 200 and json.loads(body)["body"] == payload.decode()
        status, _headers, _body = request("/api/v1/payfast/itn/", body=payload)
        assert status == 502, status
        writes = []
        for item in original:
            content = run("docker", "exec", item, "cat", "/tmp/synthetic-writes.jsonl")
            writes.extend(json.loads(line) for line in content.splitlines())
        assert writes == [{"body": payload.decode()}], writes
        print("PASS private response isolation, private paths, exact POST body and no write replay", flush=True)

        victim, survivor = original
        run("docker", "stop", "--time", "2", victim)
        observe(identities([survivor]))
        print("PASS surviving backend receives subsequent requests after one replica stops", flush=True)

        run("docker", "rm", victim)
        compose("up", "-d", "--scale", "web=2", "--no-recreate", "web")
        replacements = instances()
        assert len(replacements) == 2 and victim not in replacements
        observe(identities(replacements))
        assert compose("ps", "-q", "nginx") == proxy
        print("PASS replacement replica discovered without restarting Nginx", flush=True)

        compose("up", "-d", "--scale", "web=3", "--no-recreate", "web")
        scaled = instances()
        assert len(scaled) == 3, scaled
        observe(identities(scaled))
        assert compose("ps", "-q", "nginx") == proxy
        print("PASS scale-out to three backends discovered without restarting Nginx", flush=True)
    except Exception:
        print(compose("logs", "--no-color", "--tail", "100", check=False))
        raise
    finally:
        print(compose("down", "--volumes", "--remove-orphans", check=False))


if __name__ == "__main__":
    main()
