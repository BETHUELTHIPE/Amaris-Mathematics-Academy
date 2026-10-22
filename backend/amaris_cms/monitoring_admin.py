"""Superuser-only, read-only gateway to private Render monitoring services."""

import json
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from django.conf import settings
from django.contrib.admin import AdminSite
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseNotAllowed, HttpResponseNotFound
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.views.decorators.csrf import csrf_exempt

from .monitoring_status import is_private_monitoring_url, monitor_statuses

PROXY_PREFIX = "/admin/monitoring/"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_QUERY_BYTES = 256 * 1024


class _NoRedirect(urllib_request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _upstreams():
    return {
        "grafana": settings.MONITORING_GRAFANA_URL,
        "prometheus": settings.MONITORING_PROMETHEUS_URL,
        "flower": settings.MONITORING_FLOWER_URL,
    }


class AmarisAdminSite(AdminSite):
    index_template = "admin/amaris_index.html"

    def get_app_list(self, request, app_label=None):
        apps = list(super().get_app_list(request, app_label))
        user = request.user
        if app_label is None and user.is_authenticated and user.is_active and user.is_staff and user.is_superuser:
            apps.append(
                {
                    "name": "Monitoring",
                    "app_label": "monitoring",
                    "app_url": reverse("admin:amaris_monitoring_home"),
                    "has_module_perms": True,
                    "models": [
                        {
                            "name": title,
                            "object_name": tool,
                            "admin_url": reverse("admin:amaris_monitoring_console", kwargs={"tool": tool}),
                            "perms": {"view": True},
                            "view_only": True,
                        }
                        for tool, title in (("grafana", "Grafana"), ("prometheus", "Prometheus"), ("flower", "Flower"))
                    ],
                }
            )
        return apps

    def get_urls(self):
        extra = [
            path(
                "monitoring/grafana/api/ds/query",
                self.admin_view(self.monitoring_query),
                name="amaris_monitoring_query",
            ),
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
                "monitoring_services": monitor_statuses(),
            },
        )

    @csrf_exempt
    def monitoring_query(self, request):
        # Grafana's frontend does not know Django's CSRF token. This exemption
        # applies only to this read-only endpoint; require an exact same-origin
        # browser request below and never expose a state-changing API here.
        return self.monitoring_console(request, "grafana", "api/ds/query")

    def monitoring_console(self, request, tool, subpath=""):
        self._require_superuser(request)
        if not settings.MONITORING_CONSOLE_ENABLED:
            return HttpResponse("Monitoring is not configured.", status=503)
        query_post = request.method == "POST" and tool == "grafana" and subpath == "api/ds/query"
        if request.method != "GET" and not query_post:
            return HttpResponseNotAllowed(["GET"])

        body = None
        if query_post:
            try:
                origin = urllib_parse.urlsplit(request.headers.get("Origin") or request.headers.get("Referer", ""))
            except ValueError:
                raise PermissionDenied("Monitoring queries require the same origin.") from None
            if origin.scheme != request.scheme or origin.netloc != request.get_host():
                raise PermissionDenied("Monitoring queries require the same origin.")
            if request.content_type != "application/json":
                return HttpResponse(status=415)
            try:
                if int(request.META.get("CONTENT_LENGTH") or 0) > MAX_QUERY_BYTES:
                    return HttpResponse(status=413)
                body = request.body
                if len(body) > MAX_QUERY_BYTES:
                    return HttpResponse(status=413)
                payload = json.loads(body)
            except (ValueError, UnicodeError):
                return HttpResponse(status=400)
            queries = payload.get("queries") if isinstance(payload, dict) else None
            if not isinstance(queries, list) or not 1 <= len(queries) <= 32:
                return HttpResponse(status=400)
            for query in queries:
                datasource = query.get("datasource") if isinstance(query, dict) else None
                if not isinstance(datasource, dict) or datasource.get("uid") not in {"amaris-prometheus", "__expr__"}:
                    return HttpResponse("Monitoring datasource is not allowed.", status=400)

        upstream = _upstreams().get(tool, "").rstrip("/")
        if not upstream:
            return HttpResponseNotFound()
        if not is_private_monitoring_url(upstream):
            return HttpResponse("Monitoring endpoint is not safely configured.", status=503)

        parts = subpath.split("/")
        if any(segment in {".", ".."} for segment in parts):
            return HttpResponseNotFound()
        if len(request.META.get("QUERY_STRING", "")) > 4096:
            return HttpResponse(status=414)

        encoded_path = urllib_parse.quote(subpath, safe="/-._~")
        prefix = f"{PROXY_PREFIX}{tool}/"
        target = f"{upstream}{prefix}{encoded_path}"
        query = request.META.get("QUERY_STRING", "")
        if query:
            target += f"?{query}"

        headers = {
            "Accept-Encoding": "identity",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": request.get_host(),
        }
        if query_post:
            headers["Content-Type"] = "application/json"
        # Docker Flower optionally retains internal HTTP basic authentication.
        # Only a server-held secret is forwarded, never browser credentials.
        if tool == "flower" and settings.MONITORING_FLOWER_BASIC_AUTH:
            import base64

            secret = base64.b64encode(settings.MONITORING_FLOWER_BASIC_AUTH.encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {secret}"

        upstream_request = urllib_request.Request(target, data=body, headers=headers, method=request.method)
        opener = urllib_request.build_opener(_NoRedirect())
        try:
            response = opener.open(upstream_request, timeout=10)
        except urllib_error.HTTPError as exc:
            response = exc
        except (urllib_error.URLError, TimeoutError, OSError):
            return HttpResponse("Monitoring service unavailable.", status=502)

        with response:
            status = response.status
            if status in (301, 302, 303, 307, 308):
                location = response.headers.get("Location", "")
                if location.startswith(prefix) and not location.startswith("//"):
                    result = HttpResponse(status=status)
                    result["Location"] = location
                    result["Cache-Control"] = "private, no-store"
                    return result
                return HttpResponse("Unsafe upstream redirect blocked.", status=502)

            if status >= 500:
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
