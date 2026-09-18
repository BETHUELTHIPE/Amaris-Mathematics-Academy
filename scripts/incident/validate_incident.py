#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
FINGERPRINT_RE = re.compile(r"^[0-9a-f]{16,64}$")
CORRELATION_RE = re.compile(r"^AMR-[A-Za-z0-9-]{8,64}$")
SAFE_TYPE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,119}$")
ALLOWED_SOURCES = {"django", "scheduled-health", "manual"}
ALLOWED_ENVIRONMENTS = {"production", "staging", "unknown"}
ALLOWED_SEVERITIES = {"error", "critical"}
ALLOWED_METHODS = {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}


def _text(value: Any, limit: int) -> str:
    raw = str(value or "")
    cleaned = "".join(ch for ch in raw if ch.isprintable())
    return cleaned[:limit]


def _path(value: Any) -> str:
    cleaned = _text(value, 240).split("?", 1)[0].split("#", 1)[0]
    return cleaned if cleaned.startswith("/") or "<" in cleaned else f"/{cleaned}"


def sanitize_incident(raw: Any) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    source = _text(payload.get("source"), 32)
    if source not in ALLOWED_SOURCES:
        source = "manual"

    environment = _text(payload.get("environment"), 32).lower()
    if environment not in ALLOWED_ENVIRONMENTS:
        environment = "unknown"

    severity = _text(payload.get("severity"), 16).lower()
    if severity not in ALLOWED_SEVERITIES:
        severity = "error"

    release_sha = _text(payload.get("release_sha"), 40).lower()
    if not SHA_RE.fullmatch(release_sha):
        release_sha = "unknown"

    event_in = payload.get("event")
    event_in = event_in if isinstance(event_in, dict) else {}

    method = _text(event_in.get("method"), 12).upper()
    if method not in ALLOWED_METHODS:
        method = "GET"

    status_code = event_in.get("status_code", 500)
    try:
        status_code = int(status_code)
    except (TypeError, ValueError):
        status_code = 500
    if status_code < 100 or status_code > 599:
        status_code = 500

    correlation_reference = _text(
        event_in.get("correlation_reference"),
        72,
    )
    if not CORRELATION_RE.fullmatch(correlation_reference):
        correlation_reference = ""

    exception_type = _text(event_in.get("exception_type"), 120)
    if not SAFE_TYPE_RE.fullmatch(exception_type):
        exception_type = (
            "HealthCheckFailure" if source == "scheduled-health" else "ApplicationError"
        )

    frames: list[dict[str, Any]] = []
    raw_frames = event_in.get("frames")
    if isinstance(raw_frames, list):
        for frame in raw_frames[:8]:
            if not isinstance(frame, dict):
                continue
            file_name = _text(frame.get("file"), 180).replace("\\", "/")
            function = _text(frame.get("function"), 120)
            try:
                line = int(frame.get("line", 0))
            except (TypeError, ValueError):
                line = 0
            if file_name and SAFE_TYPE_RE.fullmatch(function or "unknown"):
                frames.append(
                    {
                        "file": "/".join(file_name.split("/")[-3:]),
                        "line": max(0, min(line, 10_000_000)),
                        "function": function or "unknown",
                    }
                )

    event = {
        "status_code": status_code,
        "method": method,
        "path": _path(event_in.get("path") or "/"),
        "correlation_reference": correlation_reference,
        "exception_type": exception_type,
        "frames": frames,
    }

    occurred_at = _text(payload.get("occurred_at"), 64)
    fingerprint = _text(payload.get("fingerprint"), 64).lower()
    if not FINGERPRINT_RE.fullmatch(fingerprint):
        basis = "|".join(
            [
                source,
                environment,
                release_sha,
                exception_type,
                method,
                event["path"],
            ]
        )
        fingerprint = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]

    return {
        "schema_version": 1,
        "source": source,
        "environment": environment,
        "severity": severity,
        "fingerprint": fingerprint,
        "release_sha": release_sha,
        "occurred_at": occurred_at,
        "event": event,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    raw = json.loads(args.input.read_text(encoding="utf-8"))
    sanitized = sanitize_incident(raw)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(sanitized, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
