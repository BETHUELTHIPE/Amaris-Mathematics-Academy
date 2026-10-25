"""Exercise real ASGI request teardown against isolated CI PostgreSQL."""

import json
from unittest import skipUnless

from asgiref.sync import async_to_sync
from asgiref.testing import ApplicationCommunicator
from django.core.handlers.asgi import ASGIHandler
from django.db import connection
from django.http import JsonResponse
from django.test import TransactionTestCase, override_settings
from django.urls import path


def database_session(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_backend_pid()")
        pid = cursor.fetchone()[0]
    return JsonResponse({"pid": pid})


urlpatterns = [path("session/", database_session)]


@skipUnless(connection.vendor == "postgresql", "Requires isolated PostgreSQL")
@override_settings(ROOT_URLCONF=__name__, ALLOWED_HOSTS=["testserver"])
class ASGIDatabaseLifecycleTests(TransactionTestCase):
    @staticmethod
    async def request_session():
        application = ApplicationCommunicator(
            ASGIHandler(),
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "https",
                "path": "/session/",
                "raw_path": b"/session/",
                "query_string": b"",
                "headers": [(b"host", b"testserver")],
            },
        )
        await application.send_input({"type": "http.request", "body": b""})
        start = await application.receive_output(timeout=5)
        if start["status"] != 200:
            raise AssertionError(f"ASGI response status: {start['status']}")
        body = bytearray()
        while True:
            message = await application.receive_output(timeout=5)
            body.extend(message.get("body", b""))
            if not message.get("more_body", False):
                break
        await application.wait(timeout=5)
        return json.loads(body)["pid"]

    def test_twenty_requests_do_not_retain_database_sessions(self):
        # Exceeds the staging session pool's 15-client limit without load traffic.
        pids = [async_to_sync(self.request_session)() for _ in range(20)]
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE pid = ANY(%s)", [pids])
            self.assertEqual(cursor.fetchone()[0], 0, "ASGI responses retained PostgreSQL connections")
