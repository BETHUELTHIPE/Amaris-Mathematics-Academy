"""Synthetic local-only traffic for exercising the real proxy and ASGI worker."""

import asyncio
import json


async def application(scope, receive, send):
    if scope["type"] != "http":
        return
    path = scope["path"]
    if path == "/slow":
        await asyncio.sleep(0.3)
    body = b""
    while True:
        message = await receive()
        body += message.get("body", b"")
        if not message.get("more_body", False):
            break
    if path == "/stream":
        await send({"type": "http.response.start", "status": 200, "headers": [(b"x-accel-buffering", b"no")]})
        await send({"type": "http.response.body", "body": b"first\n", "more_body": True})
        await asyncio.sleep(0.5)
        await send({"type": "http.response.body", "body": b"last\n"})
        return
    headers = dict(scope["headers"])
    payload = json.dumps(
        {"body": body.decode(), "scheme": scope["scheme"], "authorization": headers.get(b"authorization", b"").decode()}
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 503 if path == "/failure" else 200,
            "headers": [(b"content-type", b"application/json"), (b"cache-control", b"private, no-store")],
        }
    )
    await send({"type": "http.response.body", "body": payload})
