"""Privacy-limited real-user Core Web Vitals ingestion and superuser p75 report.

No account, URL, query, IP, user agent, session or metric ID is persisted.
Only allowlisted coarse route/device categories and Core Web Vitals values.
"""

import hashlib
import hmac
import json
import math
import re
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import WebVitalSample

METRICS = {"LCP": 60000.0, "INP": 60000.0, "CLS": 10.0}
PAGES = frozenset(
    ("home", "courses", "course-detail", "announcements", "contact",
     "booking", "student", "tutor", "auth", "other")
)
DEVICES = frozenset(("mobile", "tablet", "desktop"))
EVENT_ID = re.compile(r"^[A-Za-z0-9_.:-]{6,128}$")


@csrf_exempt
@require_POST
@never_cache
def ingest_web_vital(request):
    """Internal frontend-to-backend POST, protected with an independent token."""
    configured = getattr(settings, "WEB_VITALS_INGEST_TOKEN", "")
    if len(configured) < 32:
        return HttpResponse(status=503)
    presented = request.headers.get("X-Amaris-RUM-Token", "")
    if not hmac.compare_digest(presented, configured):
        return HttpResponse(status=403)

    if int(request.META.get("CONTENT_LENGTH") or 0) > 768:
        return HttpResponse(status=413)
    if not request.headers.get("Content-Type", "").startswith("application/json"):
        return HttpResponse(status=415)
    if len(request.body) > 768:
        return HttpResponse(status=413)
    try:
        body = json.loads(request.body)
    except (UnicodeDecodeError, ValueError):
        return HttpResponse(status=400)
    if not isinstance(body, dict) or set(body) != {"name", "value", "id", "page", "device"}:
        return HttpResponse(status=400)

    metric = body["name"]
    page = body["page"]
    device = body["device"]
    event_id = body["id"]
    value = body["value"]
    if (
        not isinstance(metric, str)
        or metric not in METRICS
        or not isinstance(page, str)
        or page not in PAGES
        or not isinstance(device, str)
        or device not in DEVICES
        or not isinstance(event_id, str)
        or EVENT_ID.fullmatch(event_id) is None
        or type(value) not in (float, int)
        or not math.isfinite(value)
        or value < 0
        or value > METRICS[metric]
    ):
        return HttpResponse(status=400)

    # Best-effort burst control on trusted internal delivery. Never store IPs.
    burst_key = "rum:burst:" + hmac.new(
        settings.SECRET_KEY.encode(), request.META.get("REMOTE_ADDR", "").encode(), hashlib.sha256
    ).hexdigest()[:24]
    if cache.add(burst_key, 1, timeout=60):
        attempts = 1
    else:
        try:
            attempts = cache.incr(burst_key)
        except (ValueError, NotImplementedError):
            attempts = 1
    if attempts > 90:
        return HttpResponse(status=429)

    digest = hmac.new(
        settings.SECRET_KEY.encode(), f"{metric}|{event_id}".encode(), hashlib.sha256
    ).hexdigest()
    WebVitalSample.objects.update_or_create(
        event_hash=digest,
        defaults={"metric_name": metric, "value": value, "page_group": page, "device": device},
    )

    # Opportunistic cleanup (once per day), no paid cron instance required.
    if cache.add("rum:prune:lock", 1, timeout=86400):
        WebVitalSample.objects.filter(observed_at__lt=timezone.now() - timedelta(days=90)).delete()
    response = HttpResponse(status=204)
    response["Cache-Control"] = "no-store"
    return response


def _python_percentile(values, probability=0.75):
    ordered = sorted(values)
    if not ordered:
        return None
    at = (len(ordered) - 1) * probability
    low = int(math.floor(at))
    upper = int(math.ceil(at))
    return ordered[low] + (ordered[upper] - ordered[low]) * (at - low)


@require_GET
@never_cache
def web_vitals_report(request):
    if not request.user.is_authenticated or not request.user.is_active or not request.user.is_superuser:
        return JsonResponse({"detail": "Forbidden"}, status=403)

    days_text = request.GET.get("days", "28")
    if days_text not in ("7", "28", "90"):
        return JsonResponse({"detail": "days must be 7, 28 or 90"}, status=400)
    days = int(days_text)
    since = timezone.now() - timedelta(days=days)

    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT metric_name, page_group, device, COUNT(*) AS n,
                       percentile_cont(0.75) WITHIN GROUP (ORDER BY value)
                FROM content_webvitalsample
                WHERE observed_at >= %s
                GROUP BY metric_name, page_group, device
                ORDER BY page_group, device, metric_name
                """,
                [since],
            )
            rows = cursor.fetchall()
    else:
        from collections import defaultdict

        by_dimension = defaultdict(list)
        for metric, page, device, value in WebVitalSample.objects.filter(
            observed_at__gte=since
        ).values_list("metric_name", "page_group", "device", "value"):
            by_dimension[(metric, page, device)].append(value)
        rows = [
            (metric, page, device, len(values), _python_percentile(values))
            for (metric, page, device), values in sorted(by_dimension.items())
        ]

    return JsonResponse(
        {
            "period_days": days,
            "generated_at": timezone.now().isoformat(),
            "sampling": "observed client-side events (not unique users)",
            "minimum_sample_count": 20,
            "thresholds": {"LCP": 2500, "INP": 200, "CLS": 0.10},
            "groups": [
                {
                    "metric": metric,
                    "page": page,
                    "device": device,
                    "samples": count,
                    "p75": round(float(p75), 3) if count >= 20 else None,
                    "status": (
                        "insufficient_data"
                        if count < 20
                        else "good"
                        if p75 <= {"LCP": 2500, "INP": 200, "CLS": 0.10}[metric]
                        else "needs_improvement"
                    ),
                }
                for metric, page, device, count, p75 in rows
            ],
        },
        headers={"Cache-Control": "private, no-store"},
    )
