"""Loopback-only mock for testing the load generator; never capacity evidence."""

from __future__ import annotations

import argparse
import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users", required=True, type=int)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.users <= 50_000:
        parser.error("Choose 1 through 50000 mock identities.")
    students = [
        {
            "student_id": f"00000000-0000-4000-8000-{index:012x}",
            "access_token": f"offline-fixture-token-{index}",
        }
        for index in range(args.users)
    ]
    args.manifest.write_text(json.dumps({"students": students}), encoding="utf-8")
    if not args.serve:
        return
    identities = {student["access_token"]: student["student_id"] for student in students}

    class FixtureHandler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            token = self.headers.get("Authorization", "").removeprefix("Bearer ")
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            key = re.search(rb'name="idempotency_key"\r\n\r\n([A-Za-z0-9_-]+)', body)
            if (
                self.path != "/api/v1/student/video-requests/checkout/"
                or token not in identities
                or key is None
                or b'filename="capacity-test.pdf"' not in body
                or b"%PDF-1.4" not in body
            ):
                self.send_error(400)
                return
            reference = f"VRQ-{key[1].decode('ascii')}"
            payload = json.dumps(
                {
                    "request_reference": reference,
                    "status": "pending_payment",
                    "gateway_url": "https://sandbox.payfast.co.za/eng/process",
                    "fields": {
                        "amount": "450.00",
                        "m_payment_id": reference,
                        "custom_str1": identities[token],
                        "signature": "a" * 32,
                    },
                }
            ).encode()
            time.sleep(0.1)  # Make overlap deterministic for the four-user mock test.
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    ThreadingHTTPServer(("127.0.0.1", 8765), FixtureHandler).serve_forever()


if __name__ == "__main__":
    main()
