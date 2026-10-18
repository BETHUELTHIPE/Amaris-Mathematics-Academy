"""Small sequential, public GET latency sample. Never store response bodies."""

import argparse
import json
import math
import statistics
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

HOSTS = {
    "amaris-production-web.onrender.com",
    "amaris-mathematics-academy-staging.onrender.com",
}
PATHS = ["/health/ready/", "/api/v1/courses/", "/api/v1/live-classes/slots/"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--samples", type=int, default=12)
    args = parser.parse_args()
    base = urlsplit(args.base)
    if base.scheme != "https" or base.hostname not in HOSTS or base.username or base.port:
        parser.error("Unexpected public backend target")
    if not 5 <= args.samples <= 20:
        parser.error("Use 5 to 20 sequential samples per route")
    report = {
        "started_at": datetime.now(UTC).isoformat(),
        "label": args.label,
        "sha_from_render": args.sha,
        "base": args.base,
        "scope": "Single-client public GET sample; warm cache; not a load/capacity test or a browser Web Vitals test.",
        "routes": [],
    }
    for path in PATHS:
        observations = []
        # Keep cold/warmup probes separate from the reported warm-cache distribution.
        for index in range(args.samples + 2):
            result = subprocess.run(
                [
                    "curl",
                    "--silent",
                    "--show-error",
                    "--compressed",
                    "--max-time",
                    "20",
                    "--output",
                    "/dev/null",
                    "--write-out",
                    "%{json}",
                    args.base.rstrip("/") + path,
                ],
                capture_output=True,
                text=True,
                timeout=25,
                check=False,
            )
            if result.returncode:
                sample = {"status": 0, "error": "request_failed"}
            else:
                raw = json.loads(result.stdout)
                sample = {
                    "status": raw["http_code"],
                    "ttfb_ms": round(raw["time_starttransfer"] * 1000, 2),
                    "total_ms": round(raw["time_total"] * 1000, 2),
                    "download_bytes": raw["size_download"],
                }
            if index >= 2:
                observations.append(sample)
            time.sleep(0.5)
        good = [item for item in observations if item["status"] == 200]
        times = sorted(item["ttfb_ms"] for item in good)
        row = {
            "path": path,
            "samples": observations,
            "requests": len(observations),
            "successes": len(good),
            "failures": len(observations) - len(good),
            "p50_ttfb_ms": statistics.median(times) if times else None,
            "p95_ttfb_ms": times[math.ceil(0.95 * len(times)) - 1] if times else None,
        }
        report["routes"].append(row)
        print(json.dumps({k: v for k, v in row.items() if k != "samples"}), flush=True)
    report["finished_at"] = datetime.now(UTC).isoformat()
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
    return int(any(row["failures"] for row in report["routes"]))


if __name__ == "__main__":
    raise SystemExit(main())
