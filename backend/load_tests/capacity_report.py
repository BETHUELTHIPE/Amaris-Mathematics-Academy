from __future__ import annotations

import argparse
import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from load_tests.capacity import CapacityThresholds, validate_capacity_level


@dataclass(frozen=True)
class MetricSpec:
    name: str
    query: str
    required: bool = True
    maximum: float | None = None
    minimum: float | None = None
    unit: str = ""


class PrometheusClient:
    def __init__(self, base_url: str, bearer_token: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.bearer_token = bearer_token

    def query(self, expression: str) -> float:
        if not self.base_url:
            raise RuntimeError("CAPACITY_PROMETHEUS_URL is not configured.")
        url = f"{self.base_url}/api/v1/query?{urllib.parse.urlencode({'query': expression})}"
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        if self.bearer_token:
            request.add_header("Authorization", f"Bearer {self.bearer_token}")
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.load(response)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"Prometheus query failed: {exc}") from exc

        if payload.get("status") != "success":
            error = payload.get("error", "unknown error")
            raise RuntimeError(f"Prometheus returned non-success status: {error}")
        result = payload.get("data", {}).get("result", [])
        if not result:
            raise RuntimeError("Prometheus query returned no samples.")
        values: list[float] = []
        for sample in result:
            raw = sample.get("value", [None, None])[1]
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                values.append(value)
        if not values:
            raise RuntimeError("Prometheus query returned no finite numeric samples.")
        return max(values)


def container_cpu_query(service: str, window: str) -> str:
    selector = f'container_label_com_docker_compose_service="{service}"'
    return (
        "max_over_time(("
        f"100 * sum(rate(container_cpu_usage_seconds_total{{{selector}}}[1m])) "
        f"/ sum(container_spec_cpu_quota{{{selector}}} / container_spec_cpu_period{{{selector}}})"
        f")[{window}:15s])"
    )


def container_ram_query(service: str, window: str) -> str:
    selector = f'container_label_com_docker_compose_service="{service}"'
    return (
        "max_over_time(("
        f"100 * sum(container_memory_working_set_bytes{{{selector}}}) "
        f"/ sum(container_spec_memory_limit_bytes{{{selector}}})"
        f")[{window}:15s])"
    )


def redis_memory_pct_query(job: str, window: str) -> str:
    selector = f'job="{job}"'
    return (
        "max_over_time(("
        f"100 * max(redis_memory_used_bytes{{{selector}}}) "
        f"/ max(redis_memory_max_bytes{{{selector}}})"
        f")[{window}:15s])"
    )


def metric_specs(
    window_seconds: int,
    thresholds: CapacityThresholds,
) -> tuple[MetricSpec, ...]:
    window = f"{max(window_seconds, 60)}s"
    cpu_max = thresholds.infrastructure_cpu_pct
    ram_max = thresholds.infrastructure_ram_pct
    return (
        MetricSpec(
            "system_cpu_pct_max",
            f'max_over_time((100 * (1 - avg(rate(node_cpu_seconds_total{{mode="idle"}}[1m]))))[{window}:15s])',
            maximum=cpu_max,
            unit="%",
        ),
        MetricSpec(
            "system_ram_pct_max",
            f"max_over_time((100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))[{window}:15s])",
            maximum=ram_max,
            unit="%",
        ),
        MetricSpec(
            "postgres_up_min",
            f'min(min_over_time(up{{job="postgres_exporter"}}[{window}]))',
            minimum=1,
        ),
        MetricSpec(
            "postgres_connections_max",
            f"max_over_time((sum(pg_stat_activity_count))[{window}:15s])",
            unit="connections",
        ),
        MetricSpec(
            "postgres_deadlocks_increase",
            f"sum(increase(pg_stat_database_deadlocks[{window}]))",
            maximum=0,
            unit="deadlocks",
        ),
        MetricSpec(
            "postgres_cpu_pct_max",
            container_cpu_query("db", window),
            maximum=cpu_max,
            unit="%",
        ),
        MetricSpec(
            "postgres_ram_pct_max",
            container_ram_query("db", window),
            maximum=ram_max,
            unit="%",
        ),
        MetricSpec(
            "redis_up_min",
            f'min(min_over_time(up{{job="redis_exporter"}}[{window}]))',
            minimum=1,
        ),
        MetricSpec(
            "redis_memory_pct_max",
            redis_memory_pct_query("redis_exporter", window),
            maximum=ram_max,
            unit="%",
        ),
        MetricSpec(
            "redis_connected_clients_max",
            f'max(max_over_time(redis_connected_clients{{job="redis_exporter"}}[{window}]))',
            unit="clients",
        ),
        MetricSpec(
            "redis_rejected_connections_increase",
            f'sum(increase(redis_rejected_connections_total{{job="redis_exporter"}}[{window}]))',
            maximum=0,
            unit="connections",
        ),
        MetricSpec(
            "redis_cpu_pct_max",
            container_cpu_query("redis", window),
            maximum=cpu_max,
            unit="%",
        ),
        MetricSpec(
            "redis_ram_pct_max",
            container_ram_query("redis", window),
            maximum=ram_max,
            unit="%",
        ),
        MetricSpec(
            "redis_cache_up_min",
            f'min(min_over_time(up{{job="redis_cache_exporter"}}[{window}]))',
            minimum=1,
        ),
        MetricSpec(
            "redis_cache_memory_pct_max",
            redis_memory_pct_query("redis_cache_exporter", window),
            maximum=ram_max,
            unit="%",
        ),
        MetricSpec(
            "gunicorn_django_up_min",
            f'min(min_over_time(up{{job="django"}}[{window}]))',
            minimum=1,
        ),
        MetricSpec(
            "gunicorn_cpu_pct_max",
            container_cpu_query("web", window),
            maximum=cpu_max,
            unit="%",
        ),
        MetricSpec(
            "gunicorn_ram_pct_max",
            container_ram_query("web", window),
            maximum=ram_max,
            unit="%",
        ),
        MetricSpec(
            "celery_flower_up_min",
            f'min(min_over_time(up{{job="flower"}}[{window}]))',
            minimum=1,
        ),
        MetricSpec(
            "celery_worker_online_min",
            f"min(min_over_time(flower_worker_online[{window}]))",
            minimum=1,
        ),
        MetricSpec(
            "celery_executing_tasks_max",
            f"max(max_over_time(flower_worker_number_of_currently_executing_tasks[{window}]))",
            required=False,
            unit="tasks",
        ),
        MetricSpec(
            "celery_prefetched_tasks_max",
            f"max(max_over_time(flower_worker_prefetched_tasks[{window}]))",
            required=False,
            unit="tasks",
        ),
        MetricSpec(
            "celery_cpu_pct_max",
            container_cpu_query("celery_worker", window),
            maximum=cpu_max,
            unit="%",
        ),
        MetricSpec(
            "celery_ram_pct_max",
            container_ram_query("celery_worker", window),
            maximum=ram_max,
            unit="%",
        ),
    )


def package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "unknown"


def markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict[str, Any]) -> str:
    locust = report["locust"]
    provenance = report["provenance"]
    lines = [
        f"# Capacity stage: {report['target_users']:,} concurrent users",
        "",
        f"**Result:** {'PASS' if report['verified'] else 'FAIL / NOT VERIFIED'}",
        "",
        "## Provenance",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Tested at (UTC) | {markdown_cell(provenance['tested_at_utc'])} |",
        f"| Environment | {markdown_cell(report['environment'])} |",
        f"| Target host | {markdown_cell(provenance['target_host'])} |",
        f"| Target Git SHA | {markdown_cell(provenance['target_git_sha'])} |",
        f"| Target image | {markdown_cell(provenance['target_image'])} |",
        f"| Capacity harness Git SHA | {markdown_cell(provenance['capacity_harness_git_sha'])} |",
        f"| Load tool | Locust {markdown_cell(provenance['locust_version'])} |",
        f"| Runner | {markdown_cell(provenance['runner_name'])} |",
        "",
        "## Request metrics",
        "",
        "| Metric | Result |",
        "| --- | ---: |",
        f"| Maximum observed concurrent users | {locust.get('max_users_observed', 0):,} |",
        f"| Target hold observed | {locust.get('target_hold_seconds_observed', 0)} s |",
        f"| Duration | {locust.get('duration_seconds', 0)} s |",
        f"| RPS | {locust.get('rps', 0)} |",
        f"| p50 | {locust.get('p50_ms', 0)} ms |",
        f"| p90 | {locust.get('p90_ms', 0)} ms |",
        f"| p95 | {locust.get('p95_ms', 0)} ms |",
        f"| p99 | {locust.get('p99_ms', 0)} ms |",
        f"| Failure % | {locust.get('failure_pct', 0)}% |",
        f"| 5xx % | {locust.get('server_5xx_pct', 0)}% |",
        "",
        "## Infrastructure metrics",
        "",
        "| Metric | Value | Gate |",
        "| --- | ---: | --- |",
    ]
    for metric in report["infrastructure"]:
        value = metric.get("value")
        display = "MISSING" if value is None else f"{value:.3f}{metric.get('unit', '')}"
        gate = "PASS" if metric["passed"] else "FAIL"
        lines.append(f"| {metric['name']} | {display} | {gate} |")

    lines.extend(["", "## Verification failures", ""])
    if report["failures"]:
        lines.extend(f"- {failure}" for failure in report["failures"])
    else:
        lines.append("- None.")
    lines.extend(
        [
            "",
            "> This stage verifies only the tested deployment, environment and concurrency level. "
            "It does not prove any higher level. "
            "A 50,000-user claim is permitted only when the 50,000 stage itself passes.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=int, required=True)
    parser.add_argument("--locust-exit-code", type=int, default=0)
    args = parser.parse_args()

    target_users = validate_capacity_level(args.stage)
    locust_path = Path(
        os.getenv(
            "CAPACITY_LOCUST_RESULT",
            "load_tests/results/capacity-locust.json",
        )
    )
    output_dir = Path(os.getenv("CAPACITY_RESULT_DIR", "load_tests/results"))
    output_dir.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    if locust_path.exists():
        locust = json.loads(locust_path.read_text(encoding="utf-8"))
    else:
        locust = {}
        failures.append("Locust evidence file is missing.")

    if args.locust_exit_code != 0:
        failures.append(f"Locust exited with status {args.locust_exit_code}.")
    if locust.get("target_users") != target_users:
        failures.append("Locust evidence does not match the requested capacity stage.")
    if not locust.get("locust_gate_passed", False):
        failures.extend(
            str(item)
            for item in locust.get(
                "locust_gate_failures",
                ["Locust gate did not pass."],
            )
        )

    target_git_sha = os.getenv("CAPACITY_TARGET_GIT_SHA", "").strip()
    target_image = os.getenv("CAPACITY_TARGET_IMAGE", "").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40}", target_git_sha):
        failures.append("CAPACITY_TARGET_GIT_SHA must identify the exact 40-character deployed Git SHA.")
    if not target_image:
        failures.append("CAPACITY_TARGET_IMAGE is required for reproducible capacity evidence.")
    elif target_image.endswith(":latest"):
        failures.append("CAPACITY_TARGET_IMAGE must be immutable; :latest is not accepted.")

    target_url = os.getenv("LOADTEST_TARGET_URL", "")
    target_host = (urllib.parse.urlparse(target_url).hostname or "").lower()
    provenance = {
        "tested_at_utc": datetime.now(UTC).isoformat(),
        "target_host": target_host,
        "target_git_sha": target_git_sha,
        "target_image": target_image,
        "capacity_harness_git_sha": os.getenv("GITHUB_SHA", "").strip(),
        "workflow_run_id": os.getenv("GITHUB_RUN_ID", "").strip(),
        "locust_version": package_version("locust"),
        "python_version": os.sys.version.split()[0],
        "runner_name": os.getenv("RUNNER_NAME", "").strip(),
        "runner_os": os.getenv("RUNNER_OS", "").strip(),
        "runner_arch": os.getenv("RUNNER_ARCH", "").strip(),
    }

    thresholds = CapacityThresholds.from_environment()
    duration = int(math.ceil(float(locust.get("duration_seconds", 0)))) + 60
    client = PrometheusClient(
        os.getenv("CAPACITY_PROMETHEUS_URL", ""),
        os.getenv("CAPACITY_PROMETHEUS_BEARER", ""),
    )

    infrastructure: list[dict[str, Any]] = []
    for spec in metric_specs(duration, thresholds):
        value: float | None = None
        error = ""
        try:
            value = client.query(spec.query)
        except RuntimeError as exc:
            error = str(exc)

        passed = value is not None
        if value is not None and spec.maximum is not None and value > spec.maximum:
            passed = False
        if value is not None and spec.minimum is not None and value < spec.minimum:
            passed = False

        if spec.required and not passed:
            if value is None:
                failures.append(f"{spec.name} was not measurable: {error}")
            else:
                failures.append(f"{spec.name}={value:.3f}{spec.unit} breached its capacity gate.")

        infrastructure.append(
            {
                "name": spec.name,
                "value": value,
                "unit": spec.unit,
                "required": spec.required,
                "maximum": spec.maximum,
                "minimum": spec.minimum,
                "passed": passed if spec.required else (value is not None),
                "error": error or None,
            }
        )

    report = {
        "target_users": target_users,
        "environment": os.getenv("LOADTEST_ENVIRONMENT", "capacity"),
        "provenance": provenance,
        "locust": locust,
        "infrastructure": infrastructure,
        "failures": failures,
        "verified": not failures,
    }
    json_path = output_dir / f"capacity-{target_users}.json"
    md_path = output_dir / f"capacity-{target_users}.md"
    json_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")

    return 0 if report["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
