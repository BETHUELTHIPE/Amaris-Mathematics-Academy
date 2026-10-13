"""Django Admin observability gateway.

Only Django superusers can view or query monitoring data. Prometheus APIs are
queried from the Django server; no monitoring tokens or private targets are
sent to the browser. Unconfigured services remain explicitly unconfigured.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.views.decorators.cache import never_cache

METRIC_JOBS = ("django", "flower", "cadvisor")
MAX_RESPONSE_BYTES = 128 * 1024


def _safe_url(value: str, *, allow_http: bool = True) -> str:
    """Reject browser-executable URLs, userinfo, fragments and invalid origins."""
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
        valid_schemes = ("https", "http") if allow_http else ("https",)
        if (
            parsed.scheme not in valid_schemes
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.port is not None
            and not (1 <= parsed.port <= 65535)
        ):
            return ""
    except ValueError:
        return ""
    return value.rstrip("/")


def _prometheus_query(endpoint: str, expression: str, token: str = "") -> list[dict]:
    """Query a trusted server-configured Prometheus origin with strict limits."""
    url = endpoint + "/api/v1/query?" + urlencode({"query": expression})
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(url, headers=headers)
    with urlopen(request, timeout=2.5) as response:
        if response.status != 200:
            raise ValueError("Prometheus returned a non-OK response.")
        payload = response.read(MAX_RESPONSE_BYTES + 1)
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError("Prometheus response exceeds the configured size limit.")
    parsed = json.loads(payload)
    if parsed.get("status") != "success" or parsed.get("data", {}).get("resultType") != "vector":
        raise ValueError("Unexpected Prometheus response format.")
    result = parsed["data"]["result"]
    if not isinstance(result, list):
        raise ValueError("Unexpected Prometheus result.")
    return result


def _scalar(series: list[dict]) -> float | None:
    if not series:
        return None
    try:
        number = float(series[0]["value"][1])
        if number < 0 or number != number or number == float("inf"):
            return None
        return number
    except (KeyError, TypeError, ValueError, IndexError):
        return None


def _snapshot():
    endpoint = _safe_url(os.getenv("PROMETHEUS_API_URL", "").strip())
    token = os.getenv("PROMETHEUS_API_BEARER_TOKEN", "").strip()
    results = {name: {"state": "not_configured", "detail": "Prometheus is not connected."} for name in METRIC_JOBS}
    snapshot: dict[str, Any] = {"services": results, "requests_per_second": None, "server_errors_per_second": None}
    if not endpoint:
        return snapshot

    for name in METRIC_JOBS:
        results[name] = {"state": "no_data", "detail": "No current scrape data."}
    try:
        series = _prometheus_query(endpoint, "up", token=token)
        samples: dict[str, list[float]] = {name: [] for name in METRIC_JOBS}
        for item in series:
            job = item.get("metric", {}).get("job")
            if job in samples:
                value = _scalar([item])
                if value is not None:
                    samples[job].append(value)
        for job in METRIC_JOBS:
            if samples[job]:
                up = any(value >= 1 for value in samples[job])
                results[job] = {
                    "state": "up" if up else "down",
                    "detail": "Last Prometheus scrape succeeded." if up else "Last Prometheus scrape failed.",
                }
        snapshot["requests_per_second"] = _scalar(
            _prometheus_query(endpoint, "sum(rate(django_http_requests_total_by_method_total[5m]))", token=token)
        )
        snapshot["server_errors_per_second"] = _scalar(
            _prometheus_query(
                endpoint, 'sum(rate(django_http_responses_total_by_status_total{status=~"5.."}[5m]))', token=token
            )
        )
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        # Do not expose private hosts, tokens, exception messages, or log PII.
        for job in METRIC_JOBS:
            results[job] = {"state": "unreachable", "detail": "Monitoring collector is unavailable."}
        snapshot["requests_per_second"] = None
        snapshot["server_errors_per_second"] = None
    return snapshot


@never_cache
def monitoring_dashboard(request):
    """Must be wrapped with admin.site.admin_view in the Django URLconf."""
    if not request.user.is_authenticated or not request.user.is_staff or not request.user.is_superuser:
        raise PermissionDenied("Superuser monitoring access is required.")

    snapshot = _snapshot()
    grafana = _safe_url(os.getenv("GRAFANA_DASHBOARD_URL", "").strip(), allow_http=False)
    flower = _safe_url(os.getenv("FLOWER_DASHBOARD_URL", "").strip(), allow_http=False)
    cadvisor = _safe_url(os.getenv("CADVISOR_DASHBOARD_URL", "").strip(), allow_http=False)
    links = {"grafana": grafana, "flower": flower, "cadvisor": cadvisor}
    context = {
        **admin.site.each_context(request),
        "title": "Monitoring and reliability",
        "snapshot": snapshot,
        "links": links,
        "django_metrics_available": "django_prometheus" in settings.INSTALLED_APPS,
    }
    response = render(request, "admin/monitoring.html", context)
    response["Cache-Control"] = "no-store, private"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response
