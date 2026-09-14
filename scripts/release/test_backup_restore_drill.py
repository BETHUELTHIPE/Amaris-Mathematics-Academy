from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


SCRIPT = Path(__file__).with_name("backup-restore-drill.sh")
FAKE_SHA = "a" * 40
FAKE_TOKEN = "unit-test-backup-token"
RECOVERY_ID = "recovery-id-must-stay-private"


class _Handler(BaseHTTPRequestHandler):
    calls: list[dict[str, object]] = []
    restore_ok = True

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def do_POST(self) -> None:  # noqa: N802
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        payload = json.loads(body)
        self.__class__.calls.append(
            {
                "authorization": self.headers.get("Authorization"),
                "payload": payload,
            }
        )
        if payload.get("action") == "backup":
            response = {
                "status": "succeeded",
                "recovery_id": RECOVERY_ID,
            }
        elif payload.get("action") == "restore-test":
            response = {
                "status": "succeeded",
                "integrity_verified": self.__class__.restore_ok,
                "application_smoke_verified": self.__class__.restore_ok,
            }
        else:
            self.send_response(400)
            self.end_headers()
            return

        encoded = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class BackupRestoreDrillTests(unittest.TestCase):
    def setUp(self) -> None:
        _Handler.calls = []
        _Handler.restore_ok = True
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _run(self) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = Path(temp_dir) / "restore-evidence.json"
            env = os.environ.copy()
            env.update(
                {
                    "BACKUP_WEBHOOK_URL": f"http://127.0.0.1:{self.server.server_port}/backup",
                    "BACKUP_TOKEN": FAKE_TOKEN,
                    "GITHUB_SHA": FAKE_SHA,
                    "RESTORE_EVIDENCE_FILE": str(evidence_path),
                }
            )
            completed = subprocess.run(
                ["sh", str(SCRIPT), "staging"],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            evidence = (
                json.loads(evidence_path.read_text(encoding="utf-8"))
                if evidence_path.exists()
                else {}
            )
        return completed, evidence

    def test_backup_restore_drill_succeeds_without_leaking_sensitive_values(self) -> None:
        completed, evidence = self._run()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(_Handler.calls), 2)
        self.assertEqual(
            [call["payload"]["action"] for call in _Handler.calls],
            ["backup", "restore-test"],
        )
        self.assertEqual(
            _Handler.calls[1]["payload"]["recovery_id"],
            RECOVERY_ID,
        )
        self.assertTrue(
            all(
                call["authorization"] == f"Bearer {FAKE_TOKEN}"
                for call in _Handler.calls
            )
        )
        self.assertNotIn(RECOVERY_ID, completed.stdout + completed.stderr)
        self.assertNotIn(FAKE_TOKEN, completed.stdout + completed.stderr)
        self.assertNotIn(RECOVERY_ID, json.dumps(evidence))
        self.assertNotIn(FAKE_TOKEN, json.dumps(evidence))
        self.assertEqual(evidence["restore_status"], "verified")
        self.assertTrue(evidence["integrity_verified"])
        self.assertTrue(evidence["application_smoke_verified"])

    def test_restore_integrity_failure_fails_closed(self) -> None:
        _Handler.restore_ok = False
        completed, evidence = self._run()

        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(evidence, {})
        self.assertNotIn(RECOVERY_ID, completed.stdout + completed.stderr)
        self.assertNotIn(FAKE_TOKEN, completed.stdout + completed.stderr)

    def test_production_environment_is_refused(self) -> None:
        env = os.environ.copy()
        env.update(
            {
                "BACKUP_WEBHOOK_URL": f"http://127.0.0.1:{self.server.server_port}/backup",
                "BACKUP_TOKEN": FAKE_TOKEN,
                "GITHUB_SHA": FAKE_SHA,
            }
        )
        completed = subprocess.run(
            ["sh", str(SCRIPT), "production"],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(_Handler.calls, [])


if __name__ == "__main__":
    unittest.main()
