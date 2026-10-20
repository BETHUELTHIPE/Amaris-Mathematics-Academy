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

METRIC_REFRESH_SUCCESS = Gauge(
    "render_metrics_exporter_metric_refresh_success",
    "1 for a fully fetched metric family; 0 for failed or partial responses (not a data value).",
    ["metric"],
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


def _params(resource_ids, selector="resource", **extra):
    params = [(selector, resource_id) for resource_id in resource_ids]
    for key, value in extra.items():
        params.append((key, str(value)))
    return params


def _get(endpoint, resource_ids, **extra):
    response = SESSION.get(
        f"{API_BASE}/{endpoint}",
        params=_params(resource_ids, resolutionSeconds=60, **extra),
        timeout=12,
    )
    # Render documents both names, but some HTTP-latency API deployments reject
    # "resource" with 400. Retry once with the supported legacy service filter.
    # Other errors (including auth and rate limits) keep their original behavior.
    if endpoint == "http-latency" and response.status_code == 400:
        response = SESSION.get(
            f"{API_BASE}/{endpoint}",
            params=_params(resource_ids, selector="service", resolutionSeconds=60, **extra),
            timeout=12,
        )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError(f"Unexpected Render metrics payload for {endpoint}.")
    return payload


def _get_with_partial_recovery(endpoint, resource_ids, **extra):
    """Keep available data without mislabeling missing resources as zero.

    Some Render metric APIs reject a combined request with HTTP 400 when one
    service does not support that metric. Retry per service; mark the metric
    incomplete if any resource remains unsupported.
    """
    if not resource_ids:
        return [], False
    try:
        return _get(endpoint, resource_ids, **extra), True
    except requests.HTTPError as exc:
        if exc.response is None or exc.response.status_code != 400 or len(resource_ids) < 2:
            LOG.warning("Render metric %s unavailable (%s)", endpoint, type(exc).__name__)
            return [], False
        series = []
        complete = True
        for resource_id in resource_ids:
            try:
                series.extend(_get(endpoint, [resource_id], **extra))
            except (requests.RequestException, ValueError, RuntimeError) as partial:
                complete = False
                LOG.warning(
                    "Render %s not available for resource %s (%s)",
                    endpoint, RESOURCE_MAP.get(resource_id, "unknown"), type(partial).__name__,
                )
        return series, complete
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        LOG.warning("Render metric %s unavailable (%s)", endpoint, type(exc).__name__)
        return [], False


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
    cpu_series, cpu_ok = _get_with_partial_recovery("cpu", resource_ids)
    memory_series, memory_ok = _get_with_partial_recovery("memory", resource_ids)
    request_series, requests_ok = _get_with_partial_recovery("http-requests", SERVICE_IDS)
    latency_series, latency_ok = _get_with_partial_recovery(
        "http-latency", SERVICE_IDS, quantile=0.95
    )
    cpu_data = _aggregate(cpu_series, resource_ids, max)
    request_data = _aggregate(request_series, SERVICE_IDS, sum)
    latency_data = _aggregate(latency_series, SERVICE_IDS, max)

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

    for metric, ok in (
        ("cpu", cpu_ok), ("memory", memory_ok),
        ("http-requests", requests_ok), ("http-latency", latency_ok),
    ):
        METRIC_REFRESH_SUCCESS.labels(metric).set(1 if ok else 0)

    complete = all((cpu_ok, memory_ok, requests_ok, latency_ok))
    REFRESH_SUCCESS.set(1 if complete else 0)
    if complete:
        LAST_SUCCESS.set(time.time())
    LOG.info(
        "Render refresh complete=%s samples: cpu=%d memory=%d http_requests=%d http_latency=%d",
        complete, len(cpu_data), len(memory_by_resource), len(request_data), len(latency_data),
    )


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
