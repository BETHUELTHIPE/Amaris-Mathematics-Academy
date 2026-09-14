from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any

from load_tests.config import TRAFFIC_STAGES

FIFTY_THOUSAND_USERS = 50_000


def configured_peak_users(profile: str) -> int:
    if profile not in TRAFFIC_STAGES:
        raise ValueError(f"Unknown LOADTEST_PROFILE {profile!r}.")
    return max(users for _until_second, users, _spawn_rate in TRAFFIC_STAGES[profile])


def _float(value: object) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: object) -> int | None:
    numeric = _float(value)
    return int(numeric) if numeric is not None else None


def read_stats(stats_path: Path) -> dict[str, Any]:
    if not stats_path.exists():
        return {}

    with stats_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    aggregate = next((row for row in rows if row.get("Name") == "Aggregated"), None)
    if not aggregate:
        return {}

    requests = _int(aggregate.get("Request Count")) or 0
    failures = _int(aggregate.get("Failure Count")) or 0
    error_rate = (failures / requests) if requests else None

    return {
        "request_count": requests,
        "failure_count": failures,
        "error_rate": error_rate,
        "p95_ms": _float(aggregate.get("95%")),
        "p99_ms": _float(aggregate.get("99%")),
    }


def read_history(history_path: Path) -> dict[str, Any]:
    if not history_path.exists():
        return {}

    timestamps: list[float] = []
    user_counts: list[int] = []
    request_rates: list[float] = []

    with history_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            timestamp = _float(row.get("Timestamp"))
            users = _int(row.get("User Count"))
            rps = _float(row.get("Requests/s"))
            if timestamp is not None:
                timestamps.append(timestamp)
            if users is not None:
                user_counts.append(users)
            if rps is not None:
                request_rates.append(rps)

    duration_seconds = None
    if len(timestamps) >= 2:
        duration_seconds = max(timestamps) - min(timestamps)

    return {
        "observed_max_users": max(user_counts) if user_counts else None,
        "peak_requests_per_second": max(request_rates) if request_rates else None,
        "duration_seconds": duration_seconds,
    }


def build_capacity_evidence(
    *,
    profile: str,
    exit_code: int,
    environment_name: str,
    results_dir: Path,
    run_reference: str,
) -> dict[str, Any]:
    passed = exit_code == 0
    configured_peak = configured_peak_users(profile)
    stats = read_stats(results_dir / f"{profile}_stats.csv")
    history = read_history(results_dir / f"{profile}_stats_history.csv")
    observed_max_users = history.get("observed_max_users")

    # Capacity is verified only from a successful run with recorded observed user
    # count. The configured traffic shape is never treated as proof by itself.
    maximum_verified_users = observed_max_users if passed and observed_max_users is not None else 0
    fifty_thousand_verified = passed and maximum_verified_users >= FIFTY_THOUSAND_USERS

    return {
        "schema_version": 1,
        "production_readiness": "NOT_EVALUATED_BY_CAPACITY_TEST",
        "load_test_passed": passed,
        "test_tool": "Locust",
        "profile": profile,
        "environment": environment_name,
        "configured_peak_users": configured_peak,
        "observed_max_concurrent_users": observed_max_users,
        "maximum_verified_concurrent_users": maximum_verified_users,
        "fifty_thousand_concurrent_users_verified": fifty_thousand_verified,
        "test_duration_seconds": history.get("duration_seconds"),
        "peak_verified_requests_per_second": history.get("peak_requests_per_second") if passed else None,
        "p95_response_time_ms": stats.get("p95_ms") if passed else None,
        "p99_response_time_ms": stats.get("p99_ms") if passed else None,
        "error_rate": stats.get("error_rate") if stats else None,
        "request_count": stats.get("request_count") if stats else None,
        "failure_count": stats.get("failure_count") if stats else None,
        "capacity_evidence": run_reference,
        "verification_rule": (
            "50,000 concurrent users may be marked verified only when a successful controlled run "
            "records at least 50,000 observed simultaneous users and passes the configured acceptance thresholds."
        ),
    }


def render_markdown(evidence: dict[str, Any]) -> str:
    def value_or_na(value: object, suffix: str = "") -> str:
        if value is None:
            return "NOT ESTABLISHED"
        return f"{value}{suffix}"

    error_rate = evidence.get("error_rate")
    error_rate_text = "NOT ESTABLISHED" if error_rate is None else f"{float(error_rate) * 100:.4f}%"
    verified_50k = "YES" if evidence["fifty_thousand_concurrent_users_verified"] else "NO"

    return "\n".join(
        [
            "## Concurrent User Capacity Verification",
            "",
            "Production readiness is assessed separately from capacity. This section must not be used to infer overall production readiness.",
            "",
            "**PRODUCTION READINESS:**",
            "REPORTED SEPARATELY BY THE PRODUCTION-READINESS GATES",
            "",
            "**MAXIMUM VERIFIED CONCURRENT USERS:**",
            str(evidence["maximum_verified_concurrent_users"]),
            "",
            "**50,000 CONCURRENT USERS VERIFIED:**",
            verified_50k,
            "",
            "**CAPACITY TEST ENVIRONMENT:**",
            str(evidence["environment"]),
            "",
            "**TEST TOOL:**",
            str(evidence["test_tool"]),
            "",
            "**TEST DURATION:**",
            value_or_na(evidence.get("test_duration_seconds"), " seconds"),
            "",
            "**PEAK VERIFIED REQUEST RATE:**",
            value_or_na(evidence.get("peak_verified_requests_per_second"), " requests/second"),
            "",
            "**P95 RESPONSE TIME:**",
            value_or_na(evidence.get("p95_response_time_ms"), " ms"),
            "",
            "**P99 RESPONSE TIME:**",
            value_or_na(evidence.get("p99_response_time_ms"), " ms"),
            "",
            "**ERROR RATE:**",
            error_rate_text,
            "",
            "**CAPACITY EVIDENCE:**",
            str(evidence.get("capacity_evidence") or "NOT ESTABLISHED"),
            "",
            "**CONFIGURED PEAK USERS (NOT PROOF OF CAPACITY):**",
            str(evidence["configured_peak_users"]),
            "",
            "Never infer or extrapolate a higher concurrency level than the successful observed test evidence.",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate evidence-based concurrent-user capacity results.")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--exit-code", required=True, type=int)
    parser.add_argument("--environment", default="unknown")
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--run-reference", default="")
    args = parser.parse_args()

    args.results_dir.mkdir(parents=True, exist_ok=True)
    evidence = build_capacity_evidence(
        profile=args.profile,
        exit_code=args.exit_code,
        environment_name=args.environment,
        results_dir=args.results_dir,
        run_reference=args.run_reference,
    )

    (args.results_dir / "capacity-evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.results_dir / "capacity-summary.md").write_text(render_markdown(evidence), encoding="utf-8")

    print(render_markdown(evidence))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
