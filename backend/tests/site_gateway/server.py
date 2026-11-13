"""Synthetic frontend/backend origin for the isolated whole-site Nginx test."""

import base64
import hashlib
import json
import os
import socket
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROLE = os.environ["FIXTURE_ROLE"]
PORT = int(os.environ["FIXTURE_PORT"])
WRITES = Path("/tmp/site-writes.jsonl")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.headers.get("Upgrade", "").lower() == "websocket":
            value = self.headers.get("Sec-WebSocket-Key", "") + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
            digest = hashlib.sha1(value.encode(), usedforsecurity=False).digest()
            self.send_response(101)
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "upgrade")
            self.send_header("Sec-WebSocket-Accept", base64.b64encode(digest).decode())
            self.send_header("X-Fixture-Role", ROLE)
            self.end_headers()
            self.wfile.flush()
            self.close_connection = True
            return
        if self.path.endswith("/stream"):
            first, last = (ROLE + ":first\n").encode(), (ROLE + ":last\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(first) + len(last)))
            self.send_header("Cache-Control", "private, no-store")
            self.end_headers()
            self.wfile.write(first)
            self.wfile.flush()
            time.sleep(1)
            self.wfile.write(last)
            return
        if "cache-" in self.path or self.path.startswith(("/_next/static/cache", "/static/cache")):
            self.public_fixture()
            return
        self.respond(b"")

    def public_fixture(self):
        time.sleep(0.04)  # Controlled origin delay; never production performance evidence.
        payload = json.dumps(
            {
                "role": ROLE,
                "nonce": time.monotonic_ns(),
                "padding": "public asset " * 1500,
            }
        ).encode()
        self.send_response(503 if "cache-error" in self.path else 200)
        self.send_header(
            "Content-Type",
            "application/javascript" if "/static/" in self.path else "application/json",
        )
        self.send_header("Content-Length", str(len(payload)))
        self.send_header(
            "Cache-Control",
            ("private, no-store" if "cache-private" in self.path else "public, max-age=2"),
        )
        if "cache-cookie" in self.path:
            self.send_header("Set-Cookie", "synthetic=secret; Secure; HttpOnly")
        if "cache-vary" in self.path:
            self.send_header("Vary", "*")
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
            chunks = []
            while True:
                size = int(self.rfile.readline().strip(), 16)
                if not size:
                    self.rfile.readline()
                    break
                chunks.append(self.rfile.read(size))
                self.rfile.read(2)
            body = b"".join(chunks)
        else:
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if self.path.startswith(("/api/v1/payfast/itn/", "/api/auth-state/write-failure")):
            with WRITES.open("a") as output:
                output.write(json.dumps({"role": ROLE, "body_b64": base64.b64encode(body).decode()}) + "\n")
                output.flush()
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            self.close_connection = True
            return
        self.respond(body)

    def respond(self, body):
        payload = json.dumps(
            {
                "role": ROLE,
                "instance": socket.gethostname(),
                "path": self.path,
                "body_b64": base64.b64encode(body).decode(),
                "authorization": self.headers.get("Authorization", ""),
                "cookie": self.headers.get("Cookie", ""),
                "host": self.headers.get("Host", ""),
                "forwarded_host": self.headers.get("X-Forwarded-Host", ""),
                "scheme": self.headers.get("X-Forwarded-Proto", ""),
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("Vary", "Authorization, Cookie")
        self.send_header("Set-Cookie", "synthetic=preserved; Path=/; Secure; HttpOnly; SameSite=Lax")
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    WRITES.write_text("")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
