"""Regression coverage for unsupported ASGI protocols."""

import asyncio
from unittest.mock import AsyncMock, patch

from django.test import SimpleTestCase

from amaris_cms.asgi import application


class ASGIProtocolTests(SimpleTestCase):
    def test_unsupported_websocket_is_closed_without_entering_django(self):
        messages = []

        async def receive():
            return {"type": "websocket.connect"}

        async def send(message):
            messages.append(message)

        with patch("amaris_cms.asgi.django_application", new_callable=AsyncMock) as django_app:
            asyncio.run(
                application(
                    {"type": "websocket", "path": "/ws/unsupported/"},
                    receive,
                    send,
                )
            )
            django_app.assert_not_awaited()

        self.assertEqual(messages, [{"type": "websocket.close", "code": 1008}])

    def test_http_scope_still_uses_django(self):
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(_message):
            return None

        scope = {"type": "http", "method": "GET", "path": "/health/live/"}
        with patch("amaris_cms.asgi.django_application", new_callable=AsyncMock) as django_app:
            asyncio.run(application(scope, receive, send))
            django_app.assert_awaited_once_with(scope, receive, send)
