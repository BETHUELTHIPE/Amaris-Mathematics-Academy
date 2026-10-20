"""Bounded, server-side checks for superuser monitoring consoles.

These checks report only observed availability. They never expose internal
addresses, tokens, session cookies, or a fabricated health result.
"""

import base64
import concurrent.futures
import re
import time
from functools import lru_cache
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from django.conf import settings

TOOL_SPECS = (
    ("grafana", "Grafana", "MONITORING_GRAFANA_URL", "/admin/monitoring/grafana/api/health"),
    ("prometheus", "Prometheus", "MONITORING_PROMETHEUS_URL", "/admin/monitoring/prometheus/-/healthy"),
    ("flower", "Flower", "MONITORING_FLOWER_URL", "/admin/monitoring/flower/"),
)
TIMEOUT_SECONDS = 1.5
PROBE_MAX_BYTES = 64 * 1024


class NoRedirect(urllib_request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def is_private_monitoring_url(url):
    """Only accept preconfigured service endpoints, not arbitrary URL paths."""
    try:
        parsed = urllib_parse.urlsplit(url)
        return (
            parsed.scheme in ("http", "https")
            and bool(parsed.hostname)
            and bool(re.fullmatch(r"[a-zA-Z0-9_.-]+", parsed.hostname))
            and parsed.username is None
            and parsed.password is None
            and parsed.path in ("", "/")
            and not parsed.query
            and not parsed.fragment
            and parsed.port is not None
            and parsed.port in range(1, 65536)
        )
    except ValueError:
        return False


def _request(url):
    opener = urllib_request.build_opener(NoRedirect())
    headers = {"Accept-Encoding": "identity", "User-Agent": "Amaris-admin-health/1.0"}
    if url.endswith("/admin/monitoring/flower/") and settings.MONITORING_FLOWER_BASIC_AUTH:
        token = base64.b64encode(settings.MONITORING_FLOWER_BASIC_AUTH.encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {token}"
    req = urllib_request.Request(url, headers=headers)
    try:
        response = opener.open(req, timeout=TIMEOUT_SECONDS)
    except urllib_error.HTTPError as exc:
        response = exc
    with response:
        status = response.status
        body = response.read(PROBE_MAX_BYTES)
    return status, body


@lru_cache(maxsize=24)
def _probe(tool, endpoint, time_bucket):
    del time_bucket
    if not is_private_monitoring_url(endpoint):
        return "invalid_config"
    try:
        if tool == "render":
            status, payload = _request(endpoint.rstrip("/") + "/metrics")
            if status != 200:
                return "unavailable"
            healthy = re.search(
                rb"(?m)^render_metrics_exporter_refresh_success\\s+1(?:\\.0+)?\\s*$", payload
            )
            last = re.search(
                rb"(?m)^render_metrics_exporter_last_success_timestamp_seconds\\s+([0-9.]+)\\s*$",
                payload,
            )
            # A once-healthy exporter with stale data is not a live metric source.
            if healthy and last and 0 <= time.time() - float(last.group(1)) <= 300:
                return "reachable"
            return "degraded"
        checks = {name: path for name, _, _, path in TOOL_SPECS}
        status, _ = _request(endpoint.rstrip("/") + checks[tool])
        if status == 200:
            return "reachable"
        return "unavailable"
    except (KeyError, ValueError, urllib_error.URLError, TimeoutError, OSError):
        return "unavailable"


def monitor_statuses():
    records = []
    enabled = settings.MONITORING_CONSOLE_ENABLED
    names = (*TOOL_SPECS, ("render", "Render metrics", "MONITORING_RENDER_EXPORTER_URL", "/metrics"))
    for name, title, setting, _ in names:
        endpoint = getattr(settings, setting, "")
        configured = bool(enabled and endpoint)
        records.append(
            {
                "name": name,
                "title": title,
                "configured": configured,
                "status": "unconfigured" if not configured else "checking",
                "description": {
                    "grafana": "Dashboard panels (Django, Celery and host/service metrics).",
                    "prometheus": "PromQL, scrape targets and alert rules.",
                    "flower": "Celery task console (worker status needs separate validation).",
                    "render": "Official Render metrics exporter; freshness based on its last refresh.",
                }[name],
            }
        )
    pending = [r for r in records if r["configured"]]
    if pending:
        bucket = int(time.monotonic() // 30)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(
                    _probe,
                    record["name"],
                    getattr(
                        settings,
                        (
                            "MONITORING_RENDER_EXPORTER_URL"
                            if record["name"] == "render"
                            else "MONITORING_" + record["name"].upper() + "_URL"
                        ),
                        "",
                    ),
                    bucket,
                ): record
                for record in pending
            }
            for future, record in futures.items():
                try:
                    record["status"] = future.result(timeout=TIMEOUT_SECONDS + 0.5)
                except (concurrent.futures.TimeoutError, OSError):
                    record["status"] = "unavailable"
    return records
