"""Run the real candidate Django WSGI application over local ephemeral TLS for CI.

Only binds 127.0.0.1 and uses an isolated SQLite database. No production URLs.
"""
import os
import ssl
from pathlib import Path
from wsgiref.simple_server import WSGIRequestHandler, make_server

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")
from django.core.wsgi import get_wsgi_application  # noqa: E402

if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUM_PERSIST_ENABLED") != "true":
    raise SystemExit("BLOCK: only isolated GitHub Actions RUM test may start this server")

# CI-only observable proof: count status codes returned by the real Django
# WSGI application, never log request bodies, headers, IPs or metric values.
app = get_wsgi_application()
ack_path = Path("/tmp/amaris-rum-ci-204-count.txt")


def observed_app(environ, start_response):
    def status_only(status, headers, exc_info=None):
        if environ.get("PATH_INFO") == "/api/v1/rum/" and status.startswith("204 "):
            with ack_path.open("a", encoding="ascii") as output:
                output.write("204\n")
        # CI-only: report status and path, never cookie, token or form body.
        if environ.get("PATH_INFO") == "/admin/login/":
            print(f"CI admin login {environ.get('REQUEST_METHOD')} HTTP {status.split()[0]}", flush=True)
        return start_response(status, headers, exc_info)

    return app(environ, status_only)


class LocalTLSRequestHandler(WSGIRequestHandler):
    """The wrapped TLS socket must be HTTPS in WSGI for Django's CSRF checks."""

    def get_environ(self):
        environ = super().get_environ()
        environ["wsgi.url_scheme"] = "https"
        return environ


server = make_server("127.0.0.1", 8443, observed_app, handler_class=LocalTLSRequestHandler)
tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
tls.load_cert_chain(os.environ["RUM_E2E_CERT"], os.environ["RUM_E2E_KEY"])
server.socket = tls.wrap_socket(server.socket, server_side=True)
print("Django isolated TLS listening on localhost:8443", flush=True)
server.serve_forever()
