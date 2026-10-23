"""ASGI entrypoint for the Amaris Django backend.

Django's HTTP ASGI handler does not support WebSocket scopes. Reject unknown
WebSocket handshakes explicitly rather than forwarding them into Django and
raising an unhandled ValueError (500). Realtime WebSocket features require a
separately authenticated ASGI router when introduced.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")

django_application = get_asgi_application()


async def application(scope, receive, send):
    """Serve HTTP normally; reject unsupported WebSocket handshakes safely."""
    if scope["type"] == "websocket":
        # Closing before accept produces a denied handshake, not an HTTP 500.
        await send({"type": "websocket.close", "code": 1008})
        return

    await django_application(scope, receive, send)
