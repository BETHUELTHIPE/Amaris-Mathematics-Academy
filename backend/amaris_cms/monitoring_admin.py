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
from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from .airflow_client import AirflowUnavailable, get_workflow, get_workflow_tasks, is_configured, monitored_dags

PROXY_PREFIX = "/admin/monitoring/"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


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

    def get_urls(self):
        extra = [
            path(
                "airflow/",
                self.admin_view(self.airflow_home),
                name="amaris_airflow_home",
            ),
            path(
                "airflow/<slug:dag_id>/",
                self.admin_view(self.airflow_detail),
                name="amaris_airflow_detail",
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

    def airflow_home(self, request):
        self._require_superuser(request)
        if request.method != "GET":
            return HttpResponseNotAllowed(["GET"])
        configured = is_configured()
        workflows = []
        unavailable = False
        if configured:
            for dag_id in monitored_dags():
                try:
                    workflows.append(get_workflow(dag_id))
                except AirflowUnavailable:
                    unavailable = True
                    workflows.append({"dag_id": dag_id, "state": "unavailable"})
        return TemplateResponse(
            request,
            "admin/amaris_airflow.html",
            {
                **self.each_context(request),
                "title": "Airflow workflow monitoring",
                "airflow_configured": configured,
                "airflow_unavailable": unavailable,
                "workflows": workflows,
                "detail": None,
            },
        )

    def airflow_detail(self, request, dag_id):
        self._require_superuser(request)
        if request.method != "GET":
            return HttpResponseNotAllowed(["GET"])
        if dag_id not in monitored_dags():
            return HttpResponseNotFound()
        if not is_configured():
            return HttpResponse("Airflow is not configured.", status=503)
        try:
            summary, tasks = get_workflow_tasks(dag_id)
        except AirflowUnavailable:
            return HttpResponse("Airflow is temporarily unavailable.", status=503)
        return TemplateResponse(
            request,
            "admin/amaris_airflow.html",
            {
                **self.each_context(request),
                "title": f"Airflow: {dag_id}",
                "airflow_configured": True,
                "airflow_unavailable": False,
                "workflows": [],
                "detail": summary,
                "tasks": tasks,
            },
        )

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

    @csrf_exempt
    def monitoring_console(self, request, tool, subpath=""):
        self._require_superuser(request)
        if not settings.MONITORING_CONSOLE_ENABLED:
            return HttpResponse("Monitoring is not configured.", status=503)
        if request.method not in ("GET", "POST"):
            return HttpResponseNotAllowed(["GET", "POST"])
        if request.method == "POST":
            # Grafana uses POST for datasource queries. All Grafana writes stay blocked.
            if tool != "grafana" or subpath != "api/ds/query":
                return HttpResponseNotAllowed(["GET"])
            # Grafana does not send Django CSRF tokens: require the exact same
            # browser origin and an authenticated active Django superuser.
            if request.headers.get("Origin") != request.build_absolute_uri("/").rstrip("/"):
                return HttpResponse(status=403)
            if request.content_type != "application/json":
                return HttpResponse(status=415)
            if len(request.body) > 128 * 1024:
                return HttpResponse(status=413)
            try:
                payload = json.loads(request.body)
            except (ValueError, UnicodeError):
                return HttpResponse(status=400)
            queries = payload.get("queries") if isinstance(payload, dict) else None
            if not isinstance(queries, list) or not 1 <= len(queries) <= 32:
                return HttpResponse(status=400)
            allowed_sources = {"amaris-prometheus", "amaris-pg-staging", "amaris-pg-production", "__expr__"}
            for query in queries:
                source = query.get("datasource") if isinstance(query, dict) else None
                if not isinstance(source, dict) or source.get("uid") not in allowed_sources:
                    return HttpResponse("Monitoring datasource is not allowed.", status=400)

        upstream = _upstreams().get(tool, "").rstrip("/")
        if not upstream:
            return HttpResponseNotFound()

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
        if request.method == "POST":
            headers["Content-Type"] = "application/json"
        upstream_request = urllib_request.Request(
            target,
            headers=headers,
            data=request.body if request.method == "POST" else None,
            method=request.method,
        )
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
