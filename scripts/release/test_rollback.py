import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SHA_N = "1" * 40
SHA_N_PLUS_1 = "2" * 40
IMAGE_PREFIX = "docker.io/bethuelm/amaris-mathematics-academy"
IMAGE_N = f"{IMAGE_PREFIX}:{SHA_N}"
IMAGE_N_PLUS_1 = f"{IMAGE_PREFIX}:{SHA_N_PLUS_1}"


class DeploymentState:
    def __init__(self):
        self.image = IMAGE_N
        self.git_sha = SHA_N
        self.healthy = True
        self.events = []


class RollbackHandler(BaseHTTPRequestHandler):
    state: DeploymentState

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        action = payload["action"]
        self.state.events.append(action)

        if action == "deploy":
            self.state.image = payload["image"]
            self.state.git_sha = payload["release_sha"]
            self.state.healthy = False
        elif action == "rollback":
            self.state.image = payload["image"]
            self.state.git_sha = payload["release_sha"]
            self.state.healthy = True
        elif action != "status":
            self.send_error(400)
            return

        self._json(
            200,
            {
                "status": "accepted",
                "active": {"image": self.state.image, "git_sha": self.state.git_sha},
            },
        )

    def do_GET(self):  # noqa: N802
        if self.path != "/health/ready/":
            self.send_error(404)
            return
        tag = self.state.image.rsplit(":", 1)[1]
        status = 200 if self.state.healthy else 503
        self._json(
            status,
            {
                "status": "ready" if self.state.healthy else "unavailable",
                "version": {"git_sha": self.state.git_sha, "image_tag": tag},
            },
        )

    def _json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


class RollbackDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.state = DeploymentState()
        handler = type(
            "BoundRollbackHandler", (RollbackHandler,), {"state": self.state}
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def run_promote(
        self, image=IMAGE_N_PLUS_1, sha=SHA_N_PLUS_1, force_rollback_test=False
    ):
        with tempfile.TemporaryDirectory() as directory:
            record_path = Path(directory) / "deployment-record.json"
            env = {
                **os.environ,
                "DEPLOY_WEBHOOK_URL": f"http://127.0.0.1:{self.server.server_port}/deploy",
                "DEPLOY_TOKEN": "test-token",
                "HEALTHCHECK_URL": f"http://127.0.0.1:{self.server.server_port}/health/ready/",
                "HEALTHCHECK_ATTEMPTS": "1",
                "HEALTHCHECK_DELAY_SECONDS": "0",
                "GITHUB_SHA": sha,
                "DEPLOYMENT_RECORD_PATH": str(record_path),
                "FORCE_ROLLBACK_TEST": "true" if force_rollback_test else "false",
            }
            result = subprocess.run(
                ["sh", "scripts/release/promote.sh", "staging", image],
                cwd=REPOSITORY_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            record = (
                json.loads(record_path.read_text()) if record_path.exists() else None
            )
            return result, record

    def test_failed_n_plus_1_restores_healthy_version_n(self):
        result, record = self.run_promote()

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.state.image, IMAGE_N)
        self.assertEqual(self.state.git_sha, SHA_N)
        self.assertTrue(self.state.healthy)
        self.assertEqual(
            self.state.events, ["status", "deploy", "status", "rollback", "status"]
        )
        self.assertEqual(record["outcome"], "rolled_back")
        self.assertEqual(
            record["candidate"], {"image": IMAGE_N_PLUS_1, "git_sha": SHA_N_PLUS_1}
        )
        self.assertEqual(record["restored"], {"image": IMAGE_N, "git_sha": SHA_N})

    def test_latest_tag_is_rejected_before_deployment(self):
        result, record = self.run_promote(f"{IMAGE_PREFIX}:latest")

        self.assertEqual(result.returncode, 1)
        self.assertIn("latest tag cannot be deployed", result.stderr)
        self.assertEqual(self.state.events, [])
        self.assertIsNone(record)

    def test_forced_staging_rollback_drill_is_successful(self):
        result, record = self.run_promote(force_rollback_test=True)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.state.image, IMAGE_N)
        self.assertTrue(self.state.healthy)
        self.assertEqual(
            self.state.events, ["status", "deploy", "status", "rollback", "status"]
        )
        self.assertEqual(record["outcome"], "rollback_test_passed")


if __name__ == "__main__":
    unittest.main()
