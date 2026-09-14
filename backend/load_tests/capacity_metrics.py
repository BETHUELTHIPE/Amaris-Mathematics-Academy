from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


CAPACITY_LEVELS = (100, 500, 1_000, 2_500, 5_000, 10_000, 25_000, 50_000)
HTTP_THRESHOLDS = {
    "failure_pct": 1.0,
    "five_xx_pct": 0.1,
    "p95_ms": 1000.0,
    "p99_ms": 2000.0,
}
RESOURCE_LIMITS = {
    "host_cpu_pct": 90.0,
    "host_memory_pct": 90.0,
    "gunicorn_cpu_pct": 90.0,
    "gunicorn_memory_pct": 90.0,
    "postgres_cpu_pct": 90.0,
    "postgres_memory_pct": 90.0,
    "redis_cpu_pct": 90.0,
    "redis_memory_pct": 90.0,
    "celery_cpu_pct": 90.0,
    "celery_memory_pct": 90.0,
}


@dataclass(frozen=True)
class MetricSpec:
    label: str
    query: str
    unit: str
    required: bool = True
    p95_limit: float | None = None


def _selector(service: str, project: str) -> str:
    parts = [f'container_label_com_docker_compose_service="{service}"']
    if project:
        parts.append(f'container_label_com_docker_compose_project="{project}"')
    return "{" + ",".join(parts) + "}"


def metric_specs(project: str) -> dict[str, MetricSpec]:
    def cpu_pct(service: str) -> str:
        selector = _selector(service, project)
        return (
            f"100 * sum(rate(container_cpu_usage_seconds_total{selector}[1m])) "
            f"/ clamp_min(sum(container_spec_cpu_quota{selector}) "
            f"/ clamp_min(avg(container_spec_cpu_period{selector}), 1), 0.001)"
        )

    def memory_pct(service: str) -> str:
        selector = _selector(service, project)
        return (
            f"100 * sum(container_memory_working_set_bytes{selector}) "
            f"/ clamp_min(sum(container_spec_memory_limit_bytes{selector}), 1)"
        )

    return {
        "host_cpu_pct": MetricSpec(
            "Host CPU", '100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[1m])))', "%",
            p95_limit=RESOURCE_LIMITS["host_cpu_pct"],
        ),
        "host_memory_pct": MetricSpec(
            "Host RAM", "100 * (1 - sum(node_memory_MemAvailable_bytes) / sum(node_memory_MemTotal_bytes))", "%",
            p95_limit=RESOURCE_LIMITS["host_memory_pct"],
        ),
        "gunicorn_cpu_pct": MetricSpec(
            "Gunicorn/Django web CPU", cpu_pct("web"), "%", p95_limit=RESOURCE_LIMITS["gunicorn_cpu_pct"],
        ),
        "gunicorn_memory_pct": MetricSpec(
            "Gunicorn/Django web RAM", memory_pct("web"), "%", p95_limit=RESOURCE_LIMITS["gunicorn_memory_pct"],
        ),
        "postgres_cpu_pct": MetricSpec(
            "PostgreSQL CPU", cpu_pct("db"), "%", p95_limit=RESOURCE_LIMITS["postgres_cpu_pct"],
        ),
        "postgres_memory_pct": MetricSpec(
            "PostgreSQL RAM", memory_pct("db"), "%", p95_limit=RESOURCE_LIMITS["postgres_memory_pct"],
        ),
        "postgres_connections": MetricSpec(
            "PostgreSQL connections", "sum(pg_stat_activity_count)", "connections",
        ),
        "postgres_transactions_rps": MetricSpec(
            "PostgreSQL transactions", "sum(rate(pg_stat_database_xact_commit[1m])) + sum(rate(pg_stat_database_xact_rollback[1m]))",
            "tx/s", required=False,
        ),
        "redis_cpu_pct": MetricSpec(
            "Redis CPU", cpu_pct("redis"), "%", p95_limit=RESOURCE_LIMITS["redis_cpu_pct"],
        ),
        "redis_memory_pct": MetricSpec(
            "Redis RAM", memory_pct("redis"), "%", p95_limit=RESOURCE_LIMITS["redis_memory_pct"],
        ),
        "redis_connected_clients": MetricSpec(
            "Redis connected clients", 'max(redis_connected_clients{job="redis_exporter"})', "clients",
        ),
        "redis_commands_rps": MetricSpec(
            "Redis commands", 'sum(rate(redis_commands_processed_total{job="redis_exporter"}[1m]))', "commands/s",
            required=False,
        ),
        "celery_cpu_pct": MetricSpec(
            "Celery worker CPU", cpu_pct("celery_worker"), "%", p95_limit=RESOURCE_LIMITS["celery_cpu_pct"],
        ),
        "celery_memory_pct": MetricSpec(
            "Celery worker RAM", memory_pct("celery_worker"), "%", p95_limit=RESOURCE_LIMITS["celery_memory_pct"],
        ),
        "celery_workers_online": MetricSpec(
            "Celery workers online", "sum(flower_worker_online)", "workers", required=False,
        ),
        "celery_task_runtime_p95_seconds": MetricSpec(
            "Celery task runtime p95",
            "histogram_quantile(0.95, sum(rate(flower_task_runtime_seconds_bucket[5m])) by (le))",
            "s", required=False,
        ),
    }


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * quantile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def query_range(
    base_url: str,
    query: str,
    start: int,
    end: int,
    step: int,
    bearer: str,
) -> list[float]:
    endpoint = base_url.rstrip("/") + "/api/v1/query_range"
    url = endpoint + "?" + urllib.parse.urlencode({
        "query": query,
        "start": str(start),
        "end": str(end),
        "step": str(step),
    })
    request = urllib.request.Request(url)
    if bearer:
        request.add_header("Authorization", f"Bearer {bearer}")
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.load(response)
    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus query failed with status {payload.get('status')!r}")
    values: list[float] = []
    for series in payload.get("data", {}).get("result", []):
        for _timestamp, raw in series.get("values", []):
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                values.append(value)
    return values


def read_aggregate_stats(prefix: Path) -> dict[str, float]:
    stats_path = Path(f"{prefix}_stats.csv")
    if not stats_path.exists():
        raise FileNotFoundError(f"Missing Locust statistics: {stats_path}")
    with stats_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    aggregate = next((row for row in rows if row.get("Name") == "Aggregated"), None)
    if aggregate is None:
        raise RuntimeError("Locust statistics do not contain the Aggregated row.")

    def number(column: str) -> float:
        raw = (aggregate.get(column) or "0").strip()
        try:
            return float(raw)
        except ValueError as exc:
            raise RuntimeError(f"Invalid {column!r} in Locust aggregate row: {raw!r}") from exc

    requests = number("Request Count")
    failures = number("Failure Count")
    return {
        "requests": requests,
        "failures": failures,
        "failure_pct": (failures / requests * 100.0) if requests else 100.0,
        "average_rps": number("Requests/s"),
        "p50_ms": number("50%"),
        "p90_ms": number("90%"),
        "p95_ms": number("95%"),
        "p99_ms": number("99%"),
    }


def read_five_xx(prefix: Path, requests: float) -> dict[str, float]:
    failures_path = Path(f"{prefix}_failures.csv")
    count = 0.0
    if failures_path.exists():
        with failures_path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                error = row.get("Error") or ""
                if re.search(r"(?:status|HTTPError)[^0-9]*5\d\d\b", error, flags=re.IGNORECASE):
                    try:
                        count += float(row.get("Occurrences") or 0)
                    except ValueError:
                        continue
    return {
        "five_xx_count": count,
        "five_xx_pct": (count / requests * 100.0) if requests else 100.0,
    }


def read_history(prefix: Path, target_users: int) -> dict[str, float]:
    history_path = Path(f"{prefix}_stats_history.csv")
    if not history_path.exists():
        raise FileNotFoundError(f"Missing Locust full-history statistics: {history_path}")
    max_users = 0
    at_target_timestamps: list[float] = []
    peak_rps = 0.0
    with history_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            raw_users = (row.get("User Count") or "0").strip()
            try:
                users = int(float(raw_users))
            except ValueError:
                users = 0
            max_users = max(max_users, users)
            if users >= target_users:
                raw_ts = (row.get("Timestamp") or "").strip()
                try:
                    at_target_timestamps.append(float(raw_ts))
                except ValueError:
                    pass
            if row.get("Name") == "Aggregated":
                try:
                    peak_rps = max(peak_rps, float(row.get("Requests/s") or 0))
                except ValueError:
                    pass
    hold_seconds = 0.0
    if len(at_target_timestamps) >= 2:
        hold_seconds = max(at_target_timestamps) - min(at_target_timestamps)
    return {
        "max_users": float(max_users),
        "observed_hold_seconds": hold_seconds,
        "peak_rps": peak_rps,
    }


def summarise_prometheus(
    base_url: str,
    start: int,
    end: int,
    bearer: str,
    project: str,
) -> tuple[dict[str, dict[str, object]], list[str]]:
    summaries: dict[str, dict[str, object]] = {}
    errors: list[str] = []
    for key, spec in metric_specs(project).items():
        try:
            values = query_range(base_url, spec.query, start, end, max(15, int((end - start) / 240) or 15), bearer)
        except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError) as exc:
            values = []
            errors.append(f"{spec.label}: query failed ({type(exc).__name__})")
        if not values:
            summaries[key] = {
                "label": spec.label,
                "unit": spec.unit,
                "required": spec.required,
                "samples": 0,
                "mean": None,
                "p95": None,
                "max": None,
                "p95_limit": spec.p95_limit,
            }
            if spec.required:
                errors.append(f"{spec.label}: required metric produced no samples")
            continue
        summaries[key] = {
            "label": spec.label,
            "unit": spec.unit,
            "required": spec.required,
            "samples": len(values),
            "mean": statistics.fmean(values),
            "p95": percentile(values, 0.95),
            "max": max(values),
            "p95_limit": spec.p95_limit,
        }
    return summaries, errors


def format_number(value: object, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.{digits}f}"


def write_stage_markdown(path: Path, report: dict[str, object]) -> None:
    http = report["http"]
    metrics = report["metrics"]
    lines = [
        f"# Capacity stage: {report['target_users']:,} concurrent users",
        "",
        f"- Result: **{'PASS' if report['passed'] else 'FAIL'}**",
        f"- Verification mode: **{'YES' if report['verification_mode'] else 'NO (exploratory only)'}**",
        f"- Maximum observed users: **{int(report['max_users']):,}**",
        f"- Observed hold at target: **{report['observed_hold_seconds']:.0f}s**",
        f"- Average RPS: **{http['average_rps']:.2f}**",
        f"- Peak RPS: **{report['peak_rps']:.2f}**",
        "",
        "## HTTP results",
        "",
        "| Metric | Observed | Gate |",
        "|---|---:|---:|",
        f"| p50 | {http['p50_ms']:.0f} ms | measured |",
        f"| p90 | {http['p90_ms']:.0f} ms | measured |",
        f"| p95 | {http['p95_ms']:.0f} ms | <= {HTTP_THRESHOLDS['p95_ms']:.0f} ms |",
        f"| p99 | {http['p99_ms']:.0f} ms | <= {HTTP_THRESHOLDS['p99_ms']:.0f} ms |",
        f"| Failure % | {http['failure_pct']:.3f}% | <= {HTTP_THRESHOLDS['failure_pct']:.3f}% |",
        f"| 5xx % | {http['five_xx_pct']:.3f}% | <= {HTTP_THRESHOLDS['five_xx_pct']:.3f}% |",
        "",
        "## Infrastructure",
        "",
        "| Component metric | Mean | p95 | Max |",
        "|---|---:|---:|---:|",
    ]
    for metric in metrics.values():
        unit = metric["unit"]
        lines.append(
            f"| {metric['label']} | {format_number(metric['mean'])} {unit} | "
            f"{format_number(metric['p95'])} {unit} | {format_number(metric['max'])} {unit} |"
        )
    if report["failures"]:
        lines.extend(["", "## Blocking failures", ""])
        lines.extend(f"- {failure}" for failure in report["failures"])
    lines.extend([
        "",
        "This report is capacity evidence only. It does not by itself mark the application production-ready.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def collect(args: argparse.Namespace) -> int:
    prefix = Path(args.prefix)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    http = read_aggregate_stats(prefix)
    http.update(read_five_xx(prefix, http["requests"]))
    history = read_history(prefix, args.target_users)
    metrics, metric_errors = summarise_prometheus(
        args.prometheus_url,
        args.start,
        args.end,
        os.getenv("CAPACITY_PROMETHEUS_BEARER", ""),
        os.getenv("CAPACITY_COMPOSE_PROJECT", "").strip(),
    )

    failures: list[str] = []
    if args.locust_exit_code != 0:
        failures.append(f"Locust exited with code {args.locust_exit_code}")
    if not args.verification_mode:
        failures.append("verification mode was disabled; exploratory runs cannot establish verified capacity")
    if history["max_users"] < args.target_users:
        failures.append(
            f"load generator reached only {int(history['max_users']):,} of {args.target_users:,} requested users"
        )
    minimum_hold = max(0, args.hold_seconds - 30)
    if history["observed_hold_seconds"] < minimum_hold:
        failures.append(
            f"target concurrency was held for {history['observed_hold_seconds']:.0f}s; "
            f"at least {minimum_hold}s is required"
        )
    if http["failure_pct"] > HTTP_THRESHOLDS["failure_pct"]:
        failures.append(
            f"failure rate {http['failure_pct']:.3f}% exceeded {HTTP_THRESHOLDS['failure_pct']:.3f}%"
        )
    if http["five_xx_pct"] > HTTP_THRESHOLDS["five_xx_pct"]:
        failures.append(
            f"5xx rate {http['five_xx_pct']:.3f}% exceeded {HTTP_THRESHOLDS['five_xx_pct']:.3f}%"
        )
    if http["p95_ms"] > HTTP_THRESHOLDS["p95_ms"]:
        failures.append(f"p95 {http['p95_ms']:.0f}ms exceeded {HTTP_THRESHOLDS['p95_ms']:.0f}ms")
    if http["p99_ms"] > HTTP_THRESHOLDS["p99_ms"]:
        failures.append(f"p99 {http['p99_ms']:.0f}ms exceeded {HTTP_THRESHOLDS['p99_ms']:.0f}ms")
    failures.extend(metric_errors)
    for metric in metrics.values():
        limit = metric["p95_limit"]
        observed = metric["p95"]
        if limit is not None and observed is not None and observed > limit:
            failures.append(
                f"{metric['label']} p95 {observed:.2f}{metric['unit']} exceeded {limit:.2f}{metric['unit']}"
            )

    report = {
        "target_users": args.target_users,
        "verification_mode": args.verification_mode,
        "locust_exit_code": args.locust_exit_code,
        "start_epoch": args.start,
        "end_epoch": args.end,
        "duration_seconds": max(0, args.end - args.start),
        "max_users": int(history["max_users"]),
        "observed_hold_seconds": history["observed_hold_seconds"],
        "peak_rps": history["peak_rps"],
        "http": http,
        "metrics": metrics,
        "thresholds": {
            "http": HTTP_THRESHOLDS,
            "resource_p95_pct": RESOURCE_LIMITS,
        },
        "failures": failures,
        "passed": not failures,
    }
    json_path = output_dir / "summary.json"
    md_path = output_dir / "summary.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_stage_markdown(md_path, report)
    print(md_path.read_text(encoding="utf-8"))
    return 0 if report["passed"] else 1


def aggregate(args: argparse.Namespace) -> int:
    root = Path(args.results_dir)
    reports: dict[int, dict[str, object]] = {}
    for stage in CAPACITY_LEVELS:
        path = root / f"stage-{stage}" / "summary.json"
        if path.exists():
            reports[stage] = json.loads(path.read_text(encoding="utf-8"))

    maximum_verified = 0
    for stage in CAPACITY_LEVELS:
        report = reports.get(stage)
        if not report or not report.get("passed"):
            break
        maximum_verified = stage

    verified_50k = maximum_verified >= 50_000 and bool(reports.get(50_000, {}).get("passed"))
    lines = [
        "# Capacity verification summary",
        "",
        "PRODUCTION READINESS:",
        "NOT EVALUATED BY CAPACITY TESTING",
        "",
        "MAXIMUM VERIFIED CONCURRENT USERS:",
        f"{maximum_verified:,}",
        "",
        "50,000 CONCURRENT USERS VERIFIED:",
        "YES" if verified_50k else "NO",
        "",
        "| Stage | Result | Peak RPS | p95 | p99 | Failure % | 5xx % |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for stage in CAPACITY_LEVELS:
        if stage not in reports:
            continue
        report = reports[stage]
        http = report["http"]
        lines.append(
            f"| {stage:,} | {'PASS' if report['passed'] else 'FAIL'} | "
            f"{report['peak_rps']:.2f} | {http['p95_ms']:.0f} ms | {http['p99_ms']:.0f} ms | "
            f"{http['failure_pct']:.3f}% | {http['five_xx_pct']:.3f}% |"
        )
    lines.extend([
        "",
        "A higher configured user count is not treated as verified capacity unless every stage through that level passes, "
        "the requested concurrency is actually reached and held, HTTP gates pass, and required Prometheus evidence is present.",
        "",
    ])
    output_path = root / "capacity-summary.md"
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(output_path.read_text(encoding="utf-8"))
    state = {
        "maximum_verified_concurrent_users": maximum_verified,
        "verified_50000": verified_50k,
        "stages": {str(stage): bool(report.get("passed")) for stage, report in reports.items()},
    }
    (root / "capacity-summary.json").write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect and aggregate Amaris capacity evidence.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser("collect")
    collect_parser.add_argument("--prefix", required=True)
    collect_parser.add_argument("--output-dir", required=True)
    collect_parser.add_argument("--target-users", type=int, choices=CAPACITY_LEVELS, required=True)
    collect_parser.add_argument("--start", type=int, required=True)
    collect_parser.add_argument("--end", type=int, required=True)
    collect_parser.add_argument("--hold-seconds", type=int, required=True)
    collect_parser.add_argument("--prometheus-url", required=True)
    collect_parser.add_argument("--locust-exit-code", type=int, required=True)
    collect_parser.add_argument("--verification-mode", action="store_true")

    aggregate_parser = subparsers.add_parser("aggregate")
    aggregate_parser.add_argument("--results-dir", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "collect":
        return collect(args)
    if args.command == "aggregate":
        return aggregate(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
