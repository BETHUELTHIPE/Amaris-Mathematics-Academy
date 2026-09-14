#!/usr/bin/env python3
"""Fail-closed validation for sanitized staging capacity infrastructure evidence."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

LIMITS = {
    "cpu_peak_percent": 85.0,
    "memory_peak_percent": 90.0,
    "db_pool_peak_percent": 85.0,
    "redis_memory_peak_percent": 85.0,
    "queue_backlog_peak": 1000.0,
    "app_restarts": 0.0,
    "db_errors": 0.0,
    "redis_errors": 0.0,
    "worker_errors": 0.0,
}


class EvidenceError(ValueError):
    pass


def _number(payload: dict[str, Any], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError(f"{key} must be numeric")
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise EvidenceError(f"{key} must be a finite non-negative number")
    return value


def validate(
    payload: dict[str, Any],
    *,
    expected_sha: str,
    expected_users: int,
    minimum_window_seconds: int,
) -> dict[str, Any]:
    if payload.get("environment") != "staging":
        raise EvidenceError("capacity infrastructure evidence must come from staging")
    if payload.get("release_sha") != expected_sha:
        raise EvidenceError("capacity evidence release_sha does not match the tested release")
    if payload.get("capacity_users") != expected_users:
        raise EvidenceError("capacity evidence user count does not match the executed test")

    observed = _number(payload, "observation_seconds")
    if observed < minimum_window_seconds:
        raise EvidenceError(
            f"observation_seconds must be at least {minimum_window_seconds}, got {observed:g}"
        )

    failures: list[str] = []
    normalized: dict[str, float] = {}
    for key, maximum in LIMITS.items():
        value = _number(payload, key)
        normalized[key] = value
        if value > maximum:
            failures.append(f"{key}={value:g} exceeds {maximum:g}")

    if failures:
        raise EvidenceError("; ".join(failures))

    return {
        "environment": "staging",
        "release_sha": expected_sha,
        "capacity_users": expected_users,
        "observation_seconds": observed,
        "limits": LIMITS,
        "observed": normalized,
        "infrastructure_thresholds_passed": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--expected-users", required=True, type=int)
    parser.add_argument("--minimum-window-seconds", required=True, type=int)
    parser.add_argument("--sanitized-output", type=Path)
    args = parser.parse_args()

    payload = json.loads(args.evidence.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("capacity infrastructure evidence must be a JSON object")

    try:
        normalized = validate(
            payload,
            expected_sha=args.expected_sha,
            expected_users=args.expected_users,
            minimum_window_seconds=args.minimum_window_seconds,
        )
    except EvidenceError as exc:
        raise SystemExit(f"capacity infrastructure evidence failed: {exc}") from exc

    if args.sanitized_output:
        args.sanitized_output.parent.mkdir(parents=True, exist_ok=True)
        args.sanitized_output.write_text(
            json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print("Capacity infrastructure evidence: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
