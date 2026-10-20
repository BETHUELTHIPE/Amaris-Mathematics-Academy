"""Small, privacy-preserving first-party Web Vitals histogram collector.

Only server-to-server requests holding the shared Render secret can write.
The database stores *only* daily counters in fixed buckets. There are no
session IDs, student identifiers, exact URLs, IP addresses or event logs.
"""
from __future__ import annotations

import json
import math
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F, Sum
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import WebVitalBucket

# The final bin is unbounded: the report says "> last threshold".
BOUNDS = {
    "LCP": (1000, 1500, 2000, 2500, 3000, 4000, 6000, 10000, 20000, 60000),
    "INP": (50, 100, 150, 200, 300, 500, 800, 1200, 2000, 5000, 10000),
    "CLS": (0.01, 0.025, 0.05, 0.1, 0.15, 0.25, 0.5, 1, 3),
}
ROUTES = frozenset({"home", "courses", "contact", "announcements", "matric", "booking", "student", "other-public"})
DEVICES = frozenset({"mobile", "tablet", "desktop"})
NETWORKS = frozenset({"slow-2g", "2g", "3g", "4g", "unknown"})
RECORD_FIELDS = frozenset({"name", "value", "route", "device", "network"})


def bucket_for(metric: str, value: float) -> int:
    return next((i for i, bound in enumerate(BOUNDS[metric]) if value <= bound), len(BOUNDS[metric]))


def summarize_p75(*, days: int = 28, min_samples: int = 20) -> list[dict[str, object]]:
    """Approximate p75 as the upper bound of a fixed, coarse bucket."""
    start = timezone.now().date() - timedelta(days=days - 1)
    values = (
        WebVitalBucket.objects.filter(day__gte=start)
        .values("metric", "route", "device", "network", "bucket")
        .annotate(samples=Sum("count"))
        .order_by("metric", "route", "device", "network", "bucket")
    )
    groups: dict[tuple[str, str, str, str], dict[int, int]] = {}
    for row in values:
        key = (row["metric"], row["route"], row["device"], row["network"])
        bins = groups.setdefault(key, {})
        bins[row["bucket"]] = int(row["samples"])
    result = []
    for (metric, route, device, network), bins in sorted(groups.items()):
        n = sum(bins.values())
        if n < min_samples:
            continue  # Suppress small populations, rather than exposing raw events.
        rank = math.ceil(n * 0.75)
        cumulative = 0
        index = len(BOUNDS[metric])
        for b, count in sorted(bins.items()):
            cumulative += count
            if cumulative >= rank:
                index = b
                break
        bound = BOUNDS[metric][index] if index < len(BOUNDS[metric]) else None
        result.append({
            "metric": metric, "route": route, "device": device,
            "network": network, "samples": n, "p75_bound": bound,
            "over_maximum": bound is None,
        })
    return result


def _valid_record(entry: object) -> tuple[str, str, str, str, int] | None:
    if not isinstance(entry, dict) or set(entry) != RECORD_FIELDS:
        return None
    metric = entry["name"]
    route = entry["route"]
    device = entry["device"]
    network = entry["network"]
    value = entry["value"]
    if (
        not isinstance(metric, str) or metric not in BOUNDS
        or not isinstance(route, str) or route not in ROUTES
        or not isinstance(device, str) or device not in DEVICES
        or not isinstance(network, str) or network not in NETWORKS
        or isinstance(value, bool) or not isinstance(value, (float, int))
    ):
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0 or number > {"LCP": 120000, "INP": 60000, "CLS": 10}[metric]:
        return None
    return metric, route, device, network, bucket_for(metric, number)


@csrf_exempt
def collect_web_vitals(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    secret = getattr(settings, "RUM_INGEST_TOKEN", "")
    supplied = request.headers.get("X-Amaris-Rum-Token", "")
    if not secret or not secrets.compare_digest(secret, supplied):
        return HttpResponse(status=403, headers={"Cache-Control": "no-store"})
    if request.content_type != "application/json" or len(request.body) > 1800:
        return HttpResponse(status=400, headers={"Cache-Control": "no-store"})
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeError):
        return HttpResponse(status=400, headers={"Cache-Control": "no-store"})
    if not isinstance(data, dict) or set(data) != {"records"}:
        return HttpResponse(status=400, headers={"Cache-Control": "no-store"})
    entries = data["records"]
    if not isinstance(entries, list) or not (1 <= len(entries) <= 3):
        return HttpResponse(status=400, headers={"Cache-Control": "no-store"})
    clean = [_valid_record(row) for row in entries]
    if any(row is None for row in clean):
        return HttpResponse(status=400, headers={"Cache-Control": "no-store"})
    today = timezone.now().date()
    with transaction.atomic():
        for metric, route, device, network, bucket in clean:
            obj, _ = WebVitalBucket.objects.get_or_create(
                day=today, metric=metric, route=route, device=device,
                network=network, bucket=bucket, defaults={"count": 0},
            )
            WebVitalBucket.objects.filter(pk=obj.pk).update(count=F("count") + 1)
        # Remove obsolete daily aggregates on approximately 1 in 100 reports.
        # No per-visitor data was ever persisted.
        if secrets.randbelow(100) == 0:
            WebVitalBucket.objects.filter(day__lt=today - timedelta(days=90)).delete()
    return HttpResponse(status=204, headers={"Cache-Control": "no-store"})
