"""Merge distributed k6 burst intervals without treating VU counts as capacity proof."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

INTERVAL = re.compile(
    r"VIDEO_SUBMISSION\|([A-Za-z0-9_-]{1,20})\|([0-9a-f]{40})\|" r"(\d+)\|(\d+)\|(\d+)\|([01])\|(\d+)(?=[\s\"']|$)"
)


def analyse(lines, *, target: int, run_id: str, deployed_sha: str, release_at_ms: int) -> dict:
    if not 1 <= target <= 50_000 or release_at_ms <= 0:
        raise ValueError("Supply a target from 1 through 50000 and a positive release timestamp.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,20}", run_id) or not re.fullmatch(r"[0-9a-f]{40}", deployed_sha):
        raise ValueError("Supply the exact run ID and deployed Git SHA.")
    seen: set[int] = set()
    events: list[tuple[int, int]] = []
    durations: list[int] = []
    starts: list[int] = []
    failures: list[str] = []
    invalid = 0
    server_errors = 0
    for line in lines:
        if "VIDEO_SUBMISSION|" not in line:
            continue
        match = INTERVAL.search(line)
        if match is None:
            failures.append("Malformed interval evidence.")
            continue
        run, sha, ordinal, begin, finish, valid, status = match.groups()
        ordinal, begin, finish, status = map(int, (ordinal, begin, finish, status))
        if run != run_id or sha != deployed_sha:
            failures.append("Interval belongs to a different run or deployed revision.")
            continue
        if ordinal in seen or not 1 <= ordinal <= target or finish <= begin:
            failures.append("Duplicate identity ordinal, invalid partition or invalid interval.")
            continue
        seen.add(ordinal)
        events.extend(((begin, 1), (finish, -1)))
        durations.append(finish - begin)
        starts.append(begin)
        invalid += valid != "1" or status != 201
        server_errors += status >= 500
    active = peak = 0
    for _, change in sorted(events):  # End before start when timestamps tie.
        active += change
        peak = max(peak, active)
    durations.sort()

    def percentile(fraction: float) -> int:
        return durations[max(0, math.ceil(len(durations) * fraction) - 1)] if durations else 0

    if len(seen) != target:
        failures.append(f"Only {len(seen)} of {target} distinct submissions completed.")
    if peak < target:
        failures.append(f"Peak measured client in-flight requests was {peak}, below {target}.")
    if invalid:
        failures.append(f"{invalid} submissions failed checkout contract validation.")
    if starts and (min(starts) < release_at_ms or max(starts) > release_at_ms + 1_000):
        failures.append("All submissions must start within one second of the shared release time.")
    if percentile(0.95) > 1_000 or percentile(0.99) > 2_000:
        failures.append("Existing latency gates breached: p95 <=1000 ms and p99 <=2000 ms.")
    if seen and server_errors / len(seen) > 0.001:
        failures.append("Existing 5xx gate breached: at most 0.1 percent.")
    return {
        "target_simultaneous_submissions": target,
        "run_id": run_id,
        "deployed_sha": deployed_sha,
        "distinct_completed_submissions": len(seen),
        "peak_client_inflight": peak,
        "invalid_submissions": invalid,
        "server_errors": server_errors,
        "p95_client_elapsed_ms": percentile(0.95),
        "p99_client_elapsed_ms": percentile(0.99),
        "dispatch_spread_ms": max(starts) - min(starts) if starts else None,
        "client_burst_gate_passed": not failures,
        # Client intervals include connection/OS queues. Server observations,
        # DB reconciliation and dependency metrics are separate release gates.
        "server_capacity_verified": False,
        "failures": sorted(set(failures)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", type=Path)
    parser.add_argument("--users", type=int, default=50_000)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--deployed-sha", required=True)
    parser.add_argument("--release-at-ms", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    def lines():
        for path in args.logs:
            with path.open(encoding="utf-8") as stream:
                yield from stream

    report = analyse(
        lines(),
        target=args.users,
        run_id=args.run_id,
        deployed_sha=args.deployed_sha,
        release_at_ms=args.release_at_ms,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["client_burst_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
