"""Read-only, superuser-gated entrypoint to self-hosted monitoring consoles.

The upstreams are fixed Docker service names, not browser-supplied URLs. Never
publish their ports or expose the monitoring Docker network to the internet.
"""
import base64
import os
from pathlib import Path
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from django.conf import settings
from django.contrib.admin import AdminSite
from django.core.exceptions import PermissionDenied
from django.http import (
    HttpResponse,
    HttpResponseNotAllowed,
    HttpResponseNotFound,
)
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.crypto import constant_time_compare


# Tools deliberately cannot be configured by the requesting browser.
UPSTREAMS = {
    "grafana": "http://grafana:3000",
    "prometheus": "http://prometheus:9090",
    "flower": "http://flower:5555",
}
PROXY_PREFIX = "/admin/monitoring/"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


def _secret_from_file(path):
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


class MetricsAccessMiddleware:
    """Hide Django's metrics endpoint unless a configured scraper token is sent.

    Even a direct connection to Render must not disclose /metrics. In production,
    an unset token means the endpoint is unavailable (fail closed).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.rstrip("/") == "/metrics":
            token = _secret_from_file(getattr(settings, "MONITORING_METRICS_TOKEN_FILE", ""))
            if not token:
                token = os.environ.get("MONITORING_METRICS_TOKEN", "").strip()
            if token or not settings.DEBUG:
                bearer = request.headers.get("Authorization", "")
                if not token or not constant_time_compare(bearer, f"Bearer {token}"):
                    return HttpResponseNotFound()
        return self.get_response(request)


class _NoRedirect(urllib_request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class AmarisAdminSite(AdminSite):
    """Django Admin dashboard with a private monitoring section."""

    index_template = "admin/amaris_index.html"

    def get_urls(self):
        extra = [
            path(
                "monitoring/",
                self.admin_view(self.monitoring_home),
                name="amaris_monitoring_home",
            ),
            path(
                "monitoring/<slug:tool>/",
                self.admin_view(self.monitoring_console),
                name="amaris_monitoring_console",
            ),
            path(
                "monitoring/<slug:tool>/<path:subpath>",
                self.admin_view(self.monitoring_console),
                name="amaris_monitoring_proxy",
            ),
        ]
        return extra + super().get_urls()

    @staticmethod
    def _require_superuser(request):
        user = request.user
        if not (user.is_authenticated and user.is_active and user.is_staff and user.is_superuser):
            raise PermissionDenied("Monitoring is reserved for Django superusers.")

    def monitoring_home(self, request):
        self._require_superuser(request)
        return TemplateResponse(
            request,
            "admin/amaris_monitoring.html",
            {
                **self.each_context(request),
                "title": "Monitoring and operations",
                "monitoring_enabled": settings.MONITORING_CONSOLE_ENABLED,
            },
        )

    def monitoring_console(self, request, tool, subpath=""):
        self._require_superuser(request)
        if not settings.MONITORING_CONSOLE_ENABLED:
            return HttpResponse(
                "Monitoring is not configured on this Django host.", status=503
            )
        if request.method != "GET":
            return HttpResponseNotAllowed(["GET"])
        if tool not in UPSTREAMS:
            return HttpResponseNotFound()

        # Do not allow a path traversal or a URL supplied by the client.
        parts = subpath.split("/")
        if any(segment in {".", ".."} for segment in parts):
            return HttpResponseNotFound()
        if len(request.META.get("QUERY_STRING", "")) > 4096:
            return HttpResponse(status=414)

        encoded_path = urllib_parse.quote(subpath, safe="/-._~")
        prefix = f"{PROXY_PREFIX}{tool}/"
        # Grafana, Prometheus, and Flower all run with this explicit subpath.
        target = f"{UPSTREAMS[tool]}{prefix}{encoded_path}"
        query = request.META.get("QUERY_STRING", "")
        if query:
            target += f"?{query}"

        headers = {"Accept-Encoding": "identity"}
        if tool == "flower":
            credential = _secret_from_file("/run/secrets/flower_basic_auth")
            if not credential or ":" not in credential:
                return HttpResponse("Flower credentials are not configured.", status=503)
            encoded = base64.b64encode(credential.encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {encoded}"

        upstream_request = urllib_request.Request(target, headers=headers, method="GET")
        opener = urllib_request.build_opener(_NoRedirect())
        try:
            response = opener.open(upstream_request, timeout=8)
        except urllib_error.HTTPError as exc:
            response = exc
        except (urllib_error.URLError, TimeoutError, OSError):
            return HttpResponse("Monitoring service unavailable.", status=502)

        with response:
            status = response.status
            if status in (301, 302, 303, 307, 308):
                location = response.headers.get("Location", "")
                # Only relative redirects into this same authenticated gateway.
                if location.startswith(prefix) and not location.startswith("//"):
                    result = HttpResponse(status=status)
                    result["Location"] = location
                    result["Cache-Control"] = "no-store"
                    return result
                return HttpResponse("Unsafe upstream redirect blocked.", status=502)
            if status < 200 or status >= 500:
                return HttpResponse("Monitoring service unavailable.", status=502)
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                return HttpResponse("Monitoring response too large.", status=502)
            content_type = response.headers.get("Content-Type", "application/octet-stream")
        result = HttpResponse(body, status=status, content_type=content_type)
        result["Cache-Control"] = "private, no-store"
        result["X-Content-Type-Options"] = "nosniff"
        result["Referrer-Policy"] = "same-origin"
        return result
