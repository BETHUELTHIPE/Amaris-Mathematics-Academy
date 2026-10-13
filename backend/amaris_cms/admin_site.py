from django.conf import settings
from django.contrib.admin import AdminSite
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.urls import path
from django.views.decorators.cache import never_cache

from .monitoring import MONITORING_TOOLS


def can_view_monitoring(user):
    return user.is_authenticated and user.is_active and user.is_staff and user.is_superuser


@never_cache
def monitoring_access(request):
    """NGINX auth_request expects a status, never a login-page redirect."""
    if not request.user.is_authenticated:
        status = 401
    else:
        status = 204 if can_view_monitoring(request.user) else 403
    response = HttpResponse(status=status)
    response["Vary"] = "Cookie"
    return response


class AmarisAdminSite(AdminSite):
    def get_urls(self):
        return [
            path("monitoring/", self.admin_view(self.monitoring), name="monitoring"),
        ] + super().get_urls()

    def monitoring(self, request):
        if not can_view_monitoring(request.user):
            raise PermissionDenied
        tools = [
            {"name": name, "description": description, "icon": icon, "url": settings.ADMIN_MONITORING_URLS[key]}
            for key, name, description, icon in MONITORING_TOOLS
        ]
        context = {
            **self.each_context(request),
            "title": "Monitoring",
            "monitoring_tools": tools,
        }
        return TemplateResponse(request, "admin/monitoring.html", context)
