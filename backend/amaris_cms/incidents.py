from __future__ import annotations

import hashlib
import json
import os
import re
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import request as url_request

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
CORRELATION_RE = re.compile(r"^AMR-[A-Za-z0-9-]{8,64}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MAX_FRAMES = 8
MAX_ROUTE_LENGTH = 240


class IncidentDispatchError(RuntimeError):
    pass


def _release_sha() -> str:
    value = (os.getenv("RELEASE_SHA") or os.getenv("GIT_SHA") or "").strip().lower()
    return value if SHA_RE.fullmatch(value) else "unknown"


def _safe_route(request: Any) -> str:
    resolver_match = getattr(request, "resolver_match", None)
    route = getattr(resolver_match, "route", "") if resolver_match else ""
    value = route or getattr(request, "path", "/") or "/"
    value = value.split("?", 1)[0].split("#", 1)[0]
    value = "".join(ch for ch in value if ch.isprintable())
    return value[:MAX_ROUTE_LENGTH]


def _safe_correlation_reference(request: Any) -> str:
    value = str(getattr(request, "correlation_reference", "") or "")
    return value if CORRELATION_RE.fullmatch(value) else ""


def _safe_frames(exc: BaseException) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    extracted = traceback.extract_tb(exc.__traceback__)[-MAX_FRAMES:]
    for frame in extracted:
        path = Path(frame.filename)
        safe_path = "/".join(path.parts[-3:]) if len(path.parts) >= 3 else path.name
        frames.append(
            {
                "file": safe_path[:180],
                "line": int(frame.lineno),
                "function": frame.name[:120],
            }
        )
    return frames


def build_incident(
    request: Any,
    exc: BaseException,
    *,
    source: str = "django",
    severity: str = "error",
    status_code: int = 500,
) -> dict[str, Any]:
    """Build a deliberately narrow incident payload.

    Request bodies, query strings, cookies, authorization headers, user objects,
    exception messages, local variables, and source lines are never collected.
    """

    method = str(getattr(request, "method", "UNKNOWN") or "UNKNOWN").upper()[:12]
    route = _safe_route(request)
    exception_type = type(exc).__name__[:120]
    release_sha = _release_sha()
    environment = os.getenv("APP_ENVIRONMENT", "unknown").strip().lower()[:32] or "unknown"
    fingerprint_basis = "|".join(
        [source, environment, release_sha, exception_type, method, route]
    )
    fingerprint = hashlib.sha256(fingerprint_basis.encode("utf-8")).hexdigest()[:24]

    return {
        "schema_version": 1,
        "source": source[:32],
        "environment": environment,
        "severity": severity if severity in {"error", "critical"} else "error",
        "fingerprint": fingerprint,
        "release_sha": release_sha,
        "occurred_at": datetime.now(UTC).isoformat(),
        "event": {
            "status_code": int(status_code),
            "method": method,
            "path": route,
            "correlation_reference": _safe_correlation_reference(request),
            "exception_type": exception_type,
            "frames": _safe_frames(exc),
        },
    }


def dispatch_incident_to_github(incident: dict[str, Any]) -> None:
    """Send one already-sanitized incident as a repository_dispatch event."""

    token = os.getenv("INCIDENT_GITHUB_TOKEN", "").strip()
    if not token:
        raise IncidentDispatchError("INCIDENT_GITHUB_TOKEN is required")

    repository = os.getenv(
        "INCIDENT_GITHUB_REPOSITORY",
        "BETHUELTHIPE/Amaris-Mathematics-Academy",
    ).strip()
    if not REPOSITORY_RE.fullmatch(repository):
        raise IncidentDispatchError("INCIDENT_GITHUB_REPOSITORY is invalid")

    payload = json.dumps(
        {"event_type": "production_incident", "client_payload": incident},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if len(payload) > 60_000:
        raise IncidentDispatchError("incident dispatch payload exceeds the safety limit")

    request = url_request.Request(
        f"https://api.github.com/repos/{repository}/dispatches",
        data=payload,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "amaris-production-incident-collector/1.0",
            "X-GitHub-Api-Version": "2026-03-10",
        },
        method="POST",
    )
    with url_request.urlopen(request, timeout=10) as response:  # noqa: S310
        status = int(getattr(response, "status", 0))
    if status != 204:
        raise IncidentDispatchError(f"GitHub incident dispatch returned HTTP {status}")
