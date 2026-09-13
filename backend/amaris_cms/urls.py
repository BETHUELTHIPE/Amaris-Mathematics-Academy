from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from redis import Redis

from . import error_views


def health_live(_request):
    return JsonResponse({"status": "ok"})


def _postgresql_available():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            return cursor.fetchone() == (1,)
    except Exception:  # Health responses intentionally hide connection details.
        return False


def health_ready(_request):
    ready = _postgresql_available()
    return JsonResponse(
        {
            "status": "ready" if ready else "unavailable",
            "version": {
                "git_sha": settings.RELEASE_GIT_SHA,
                "image_tag": settings.RELEASE_IMAGE_TAG,
            },
        },
        status=200 if ready else 503,
    )


def health_dependencies(_request):
    dependencies = {"postgresql": False, "redis": False}
    dependencies["postgresql"] = _postgresql_available()

    try:
        client = Redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=2)
        dependencies["redis"] = bool(client.ping())
        client.close()
    except Exception:  # Health responses intentionally hide connection details.
        pass

    critical_healthy = dependencies["postgresql"]
    state = "ok" if all(dependencies.values()) else ("degraded" if critical_healthy else "unavailable")
    return JsonResponse(
        {"status": state, "dependencies": dependencies},
        status=200 if critical_healthy else 503,
    )


urlpatterns = [
    path("errors/400/", error_views.error_400, name="error-400"),
    path("errors/403/", error_views.error_403, name="error-403"),
    path("errors/404/", error_views.error_404, name="error-404"),
    path("errors/429/", error_views.error_429, name="error-429"),
    path("errors/500/", error_views.error_500, name="error-500"),
    path("admin/", admin.site.urls),
    path("api/v1/", include("content.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="api-docs"),
    path("health/", health_live, name="health"),
    path("health/live/", health_live, name="health-live"),
    path("health/ready/", health_ready, name="health-ready"),
    path("health/dependencies/", health_dependencies, name="health-dependencies"),
    path("", include("django_prometheus.urls")),
]

handler400 = error_views.error_400
handler403 = error_views.error_403
handler404 = error_views.error_404
handler500 = error_views.error_500

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
