"""Run the real candidate Django WSGI application over local ephemeral TLS for CI.

Only binds 127.0.0.1 and uses an isolated SQLite database. No production URLs.
"""
import os
import ssl
from wsgiref.simple_server import make_server

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")
from django.core.wsgi import get_wsgi_application  # noqa: E402

if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUM_PERSIST_ENABLED") != "true":
    raise SystemExit("BLOCK: only isolated GitHub Actions RUM test may start this server")

server = make_server("127.0.0.1", 8443, get_wsgi_application())
tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
tls.load_cert_chain(os.environ["RUM_E2E_CERT"], os.environ["RUM_E2E_KEY"])
server.socket = tls.wrap_socket(server.socket, server_side=True)
print("Django isolated TLS listening on localhost:8443", flush=True)
server.serve_forever()
