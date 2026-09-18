#!/usr/bin/env python3
"""Authenticated host-side deployment webhook service.

Run this only on the deployment host, bound to loopback behind an HTTPS reverse proxy.
`migration-plan` is implemented directly and is read-only. Deployment operations are
delegated to fixed executable paths configured by the operator; request content is never
executed as shell input. `current-release` is a read-only adapter used to discover the
exact immutable image that must be restored if a release fails health checks.
"""

from __future__ import annotations

import hmac
import json
import os
import subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import host_migration_plan

MAX_BODY_BYTES = 16 * 1024
DEFAULT_PATH = "/deploy"
ACTION_EXECUTABLE_ENV = {
    "current-release": "CURRENT_RELEASE_ACTION_EXECUTABLE",
    "rollback-target": "ROLLBACK_TARGET_ACTION_EXECUTABLE",
    "deploy": "DEPLOY_ACTION_EXECUTABLE",
    "migrate": "MIGRATE_ACTION_EXECUTABLE",
    "rollback": "ROLLBACK_ACTION_EXECUTABLE",
}


class WebhookError(ValueError):
    pass


def _configured_environment() -> str:
    environment = os.environ.get("DEPLOYMENT_ENVIRONMENT", "")
    if environment not in {"staging", "production"}:
        raise WebhookError("DEPLOYMENT_ENVIRONMENT must be staging or production")
    return environment


def _validate_environment(payload: dict[str, Any]) -> str:
    configured = _configured_environment()
    requested = payload.get("environment")
    if requested != configured:
        raise WebhookError("request environment does not match this deployment host")
    return configured


def _validate_release_identity(payload: dict[str, Any]) -> None:
    image = payload.get("image")
    release_sha = payload.get("release_sha")
    if not isinstance(image, str) or not image.startswith(host_migration_plan.IMAGE_PREFIX):
        raise WebhookError("image must use the approved Amaris Docker Hub repository")
    if not isinstance(release_sha, str) or not host_migration_plan.SHA_RE.fullmatch(release_sha):
        raise WebhookError("release_sha must be a full 40-character lowercase git SHA")
    if image.removeprefix(host_migration_plan.IMAGE_PREFIX) != release_sha:
        raise WebhookError("image tag must exactly match release_sha")


def _delegate_action(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    env_name = ACTION_EXECUTABLE_ENV[action]
    executable_value = os.environ.get(env_name, "")
    if not executable_value:
        raise WebhookError(f"{env_name} is not configured")

    executable = Path(executable_value)
    if not executable.is_absolute() or not executable.is_file() or not os.access(executable, os.X_OK):
        raise WebhookError(f"{env_name} must point to an executable absolute path")

    completed = subprocess.run(
        [str(executable)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=1800,
        check=True,
    )

    if not completed.stdout.strip():
        return {"status": "succeeded", "action": action}

    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise WebhookError(f"{action} handler returned invalid JSON") from exc
    if not isinstance(response, dict):
        raise WebhookError(f"{action} handler response must be a JSON object")
    return response


def dispatch(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action")
    if action not in {"current-release", "rollback-target", "deploy", "migrate", "migration-plan", "rollback"}:
        raise WebhookError("unsupported deployment action")

    _validate_environment(payload)

    if action == "migration-plan":
        return host_migration_plan.run_migration_plan(payload)

    if action in {"current-release", "rollback-target"}:
        result = _delegate_action(action, payload)
        _validate_release_identity(result)
        if action == "rollback-target":
            rollback_safe = result.get("rollback_safe")
            if not isinstance(rollback_safe, bool):
                raise WebhookError(
                    "rollback-target handler must return boolean rollback_safe"
                )
        return result

    if action in {"deploy", "migrate", "rollback"}:
        _validate_release_identity(payload)

    return _delegate_action(action, payload)


class Handler(BaseHTTPRequestHandler):
    server_version = "AmarisDeploymentWebhook/1.0"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        # Do not log request bodies, authorization headers, image environment files or tokens.
        return

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:  # noqa: N802
        expected_path = os.environ.get("DEPLOY_WEBHOOK_PATH", DEFAULT_PATH)
        if self.path != expected_path:
            self._send_json(HTTPStatus.NOT_FOUND, {"status": "failed"})
            return

        expected_token = os.environ.get("DEPLOY_WEBHOOK_TOKEN", "")
        if not expected_token:
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "failed"})
            return

        authorization = self.headers.get("Authorization", "")
        expected_authorization = f"Bearer {expected_token}"
        if not hmac.compare_digest(authorization, expected_authorization):
            self._send_json(HTTPStatus.UNAUTHORIZED, {"status": "failed"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"status": "failed"})
            return
        if content_length <= 0 or content_length > MAX_BODY_BYTES:
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"status": "failed"})
            return

        try:
            payload = json.loads(self.rfile.read(content_length))
            if not isinstance(payload, dict):
                raise WebhookError("request body must be a JSON object")
            result = dispatch(payload)
        except (WebhookError, host_migration_plan.ContractError, json.JSONDecodeError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"status": "failed", "error": str(exc)})
            return
        except subprocess.TimeoutExpired:
            self._send_json(HTTPStatus.GATEWAY_TIMEOUT, {"status": "failed"})
            return
        except subprocess.CalledProcessError:
            self._send_json(HTTPStatus.BAD_GATEWAY, {"status": "failed"})
            return

        self._send_json(HTTPStatus.OK, result)


def main() -> int:
    # Bind to loopback by default. TLS must terminate at Nginx/load balancer before this service.
    bind = os.environ.get("DEPLOY_WEBHOOK_BIND", "127.0.0.1")
    port = int(os.environ.get("DEPLOY_WEBHOOK_PORT", "9080"))
    _configured_environment()
    if not os.environ.get("DEPLOY_WEBHOOK_TOKEN"):
        raise SystemExit("DEPLOY_WEBHOOK_TOKEN is required")

    server = ThreadingHTTPServer((bind, port), Handler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
