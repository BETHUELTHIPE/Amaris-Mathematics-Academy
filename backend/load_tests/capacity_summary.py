from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from load_tests.capacity import progressive_levels, validate_capacity_level


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requested", type=int, required=True)
    args = parser.parse_args()

    requested = validate_capacity_level(args.requested)
    result_dir = Path("load_tests/results")
    stage_results: list[dict[str, Any]] = []
    maximum_verified = 0
    contiguous = True

    for level in progressive_levels(requested):
        path = result_dir / f"capacity-{level}.json"
        if not path.exists():
            stage_results.append({"target_users": level, "verified": False, "reason": "stage evidence missing"})
            contiguous = False
            continue

        report = json.loads(path.read_text(encoding="utf-8"))
        verified = bool(report.get("verified", False))
        stage_results.append(
            {
                "target_users": level,
                "verified": verified,
                "rps": report.get("locust", {}).get("rps"),
                "p50_ms": report.get("locust", {}).get("p50_ms"),
                "p90_ms": report.get("locust", {}).get("p90_ms"),
                "p95_ms": report.get("locust", {}).get("p95_ms"),
                "p99_ms": report.get("locust", {}).get("p99_ms"),
                "failure_pct": report.get("locust", {}).get("failure_pct"),
                "server_5xx_pct": report.get("locust", {}).get("server_5xx_pct"),
            }
        )
        if contiguous and verified:
            maximum_verified = level
        else:
            contiguous = False

    verified_50k = maximum_verified >= 50_000
    summary = {
        "requested_max_users": requested,
        "maximum_verified_concurrent_users": maximum_verified,
        "verified_50000": verified_50k,
        "stages": stage_results,
    }
    (result_dir / "capacity-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Capacity test summary",
        "",
        f"**MAXIMUM VERIFIED CONCURRENT USERS:** {maximum_verified:,}",
        "",
        f"**50,000 CONCURRENT USERS VERIFIED:** {'YES' if verified_50k else 'NO'}",
        "",
        "| Stage | Result | RPS | p50 | p90 | p95 | p99 | Failure % | 5xx % |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for stage in stage_results:
        lines.append(
            "| {target:,} | {result} | {rps} | {p50} | {p90} | {p95} | {p99} | {failure} | {five_xx} |".format(
                target=stage["target_users"],
                result="PASS" if stage.get("verified") else "FAIL / NOT VERIFIED",
                rps=stage.get("rps", "-"),
                p50=stage.get("p50_ms", "-"),
                p90=stage.get("p90_ms", "-"),
                p95=stage.get("p95_ms", "-"),
                p99=stage.get("p99_ms", "-"),
                failure=stage.get("failure_pct", "-"),
                five_xx=stage.get("server_5xx_pct", "-"),
            )
        )
    lines.extend(
        [
            "",
            "Capacity is verified only through the highest contiguous passing stage. "
            "No higher capacity is inferred or extrapolated.",
            "",
        ]
    )
    (result_dir / "capacity-summary.md").write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
