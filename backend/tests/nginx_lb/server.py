"""Disposable HTTP backend for real Nginx discovery and write-replay checks."""

import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WRITES = Path("/tmp/synthetic-writes.jsonl")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        self.respond(b"")

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if self.path == "/api/v1/payfast/itn/":
            with WRITES.open("a") as output:
                output.write(json.dumps({"body": body.decode()}) + "\n")
                output.flush()
            # Simulate a write accepted by an application before its connection dies.
            # A proxy retry could duplicate a booking or payment operation.
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            self.close_connection = True
            return
        self.respond(body)

    def respond(self, body):
        payload = json.dumps(
            {
                "instance": socket.gethostname(),
                "authorization": self.headers.get("Authorization", ""),
                "body": body.decode(),
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("Vary", "Authorization, Cookie")
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    WRITES.write_text("")
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
