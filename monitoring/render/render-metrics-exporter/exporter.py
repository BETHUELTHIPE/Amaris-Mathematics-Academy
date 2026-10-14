import logging
import os
import time
from collections import defaultdict

import requests
from prometheus_client import Gauge, start_http_server

API_BASE = "https://api.render.com/v1/metrics"
API_KEY = os.environ.get("RENDER_API_KEY", "").strip()
PORT = int(os.environ.get("PORT", "10000"))
INTERVAL = max(30, int(os.environ.get("SCRAPE_INTERVAL_SECONDS", "60")))

RESOURCE_MAP = {}
for item in os.environ.get("RENDER_RESOURCES", "").split(","):
    item = item.strip()
    if not item:
        continue
    resource_id, sep, resource_name = item.partition("=")
    if not sep or not resource_id.strip() or not resource_name.strip():
        raise SystemExit("RENDER_RESOURCES must contain id=name pairs.")
    RESOURCE_MAP[resource_id.strip()] = resource_name.strip()

SERVICE_IDS = [
    item.strip()
    for item in os.environ.get("RENDER_SERVICE_IDS", "").split(",")
    if item.strip()
]

if not API_KEY:
    raise SystemExit("RENDER_API_KEY is required.")
if not RESOURCE_MAP:
    raise SystemExit("RENDER_RESOURCES is required.")
if not SERVICE_IDS:
    raise SystemExit("RENDER_SERVICE_IDS is required.")

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
LOG = logging.getLogger("render-metrics-exporter")

CPU = Gauge(
    "render_service_cpu_usage",
    "Latest Render CPU usage value reported by the Render metrics API.",
    ["resource_id", "resource_name", "unit"],
)
MEMORY = Gauge(
    "render_service_memory_usage_bytes",
    "Latest Render memory usage normalized to bytes.",
    ["resource_id", "resource_name"],
)
HTTP_REQUESTS = Gauge(
    "render_service_http_requests_window",
    "Latest Render HTTP request-count sample for the API resolution window.",
    ["resource_id", "resource_name", "unit"],
)
HTTP_LATENCY = Gauge(
    "render_service_http_latency_p95_seconds",
    "Latest Render p95 HTTP latency normalized to seconds.",
    ["resource_id", "resource_name"],
)
REFRESH_SUCCESS = Gauge(
    "render_metrics_exporter_refresh_success",
    "1 when the most recent Render API refresh completed successfully.",
)
LAST_SUCCESS = Gauge(
    "render_metrics_exporter_last_success_timestamp_seconds",
    "Unix timestamp of the most recent successful Render API refresh.",
)

SESSION = requests.Session()
SESSION.headers.update(
    {
        "Accept": "application/json",
        "Authorization": f"Bearer {API_KEY}",
        "User-Agent": "amaris-render-metrics-exporter/1.0",
    }
)


def _labels(series):
    return {
        str(item.get("field", "")): str(item.get("value", ""))
        for item in series.get("labels", [])
        if item.get("field")
    }


def _resource_id(series):
    labels = _labels(series)
    return (
        labels.get("resource")
        or labels.get("service")
        or labels.get("redis")
        or labels.get("keyValue")
        or ""
    )


def _latest(series):
    values = series.get("values") or []
    if not values:
        return None
    return values[-1].get("value")


def _params(resource_ids, **extra):
    params = [("resource", resource_id) for resource_id in resource_ids]
    for key, value in extra.items():
        params.append((key, str(value)))
    return params


def _get(endpoint, resource_ids, **extra):
    response = SESSION.get(
        f"{API_BASE}/{endpoint}",
        params=_params(resource_ids, resolutionSeconds=60, **extra),
        timeout=12,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError(f"Unexpected Render metrics payload for {endpoint}.")
    return payload


def _normalize_bytes(value, unit):
    if value is None:
        return None
    factor = {
        "b": 1,
        "byte": 1,
        "bytes": 1,
        "kb": 1024,
        "kib": 1024,
        "mb": 1024**2,
        "mib": 1024**2,
        "gb": 1024**3,
        "gib": 1024**3,
    }.get(str(unit).strip().lower(), 1)
    return float(value) * factor


def _normalize_seconds(value, unit):
    if value is None:
        return None
    factor = {
        "s": 1,
        "sec": 1,
        "second": 1,
        "seconds": 1,
        "ms": 1e-3,
        "millisecond": 1e-3,
        "milliseconds": 1e-3,
        "us": 1e-6,
        "µs": 1e-6,
        "ns": 1e-9,
    }.get(str(unit).strip().lower(), 1)
    return float(value) * factor


def _aggregate(series_list, resource_ids, reducer):
    values = defaultdict(list)
    units = {}
    for series in series_list:
        resource_id = _resource_id(series)
        if resource_id not in resource_ids:
            continue
        latest = _latest(series)
        if latest is None:
            continue
        values[resource_id].append(float(latest))
        units[resource_id] = str(series.get("unit") or "")
    result = {}
    for resource_id, samples in values.items():
        result[resource_id] = (reducer(samples), units.get(resource_id, ""))
    return result


def refresh():
    resource_ids = list(RESOURCE_MAP)
    cpu_data = _aggregate(_get("cpu", resource_ids), resource_ids, max)
    memory_series = _get("memory", resource_ids)
    request_data = _aggregate(
        _get("http-requests", SERVICE_IDS),
        SERVICE_IDS,
        sum,
    )
    latency_data = _aggregate(
        _get("http-latency", SERVICE_IDS, quantile=0.95),
        SERVICE_IDS,
        max,
    )

    CPU.clear()
    for resource_id, (value, unit) in cpu_data.items():
        CPU.labels(resource_id, RESOURCE_MAP[resource_id], unit).set(value)

    MEMORY.clear()
    memory_by_resource = defaultdict(list)
    memory_units = {}
    for series in memory_series:
        resource_id = _resource_id(series)
        if resource_id not in RESOURCE_MAP:
            continue
        latest = _latest(series)
        if latest is None:
            continue
        memory_by_resource[resource_id].append(float(latest))
        memory_units[resource_id] = str(series.get("unit") or "")
    for resource_id, samples in memory_by_resource.items():
        normalized = [
            _normalize_bytes(value, memory_units[resource_id]) for value in samples
        ]
        MEMORY.labels(resource_id, RESOURCE_MAP[resource_id]).set(sum(normalized))

    HTTP_REQUESTS.clear()
    for resource_id, (value, unit) in request_data.items():
        HTTP_REQUESTS.labels(resource_id, RESOURCE_MAP[resource_id], unit).set(value)

    HTTP_LATENCY.clear()
    for resource_id, (value, unit) in latency_data.items():
        HTTP_LATENCY.labels(resource_id, RESOURCE_MAP[resource_id]).set(
            _normalize_seconds(value, unit)
        )

    REFRESH_SUCCESS.set(1)
    LAST_SUCCESS.set(time.time())


def main():
    start_http_server(PORT)
    LOG.info("Render metrics exporter listening on port %s", PORT)
    while True:
        try:
            refresh()
        except Exception:
            REFRESH_SUCCESS.set(0)
            LOG.exception("Render metrics refresh failed")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
