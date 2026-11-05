"""Isolated synthetic web -> task propagation scenario, invoked by tests/CI only."""

import json
import types

from celery.signals import before_task_publish
from django.conf import settings
from django.http import JsonResponse
from django.test import Client
from django.urls import path
from opentelemetry import trace

# Import the real entrypoint: instrumentation must precede middleware creation.
from amaris_cms import celery_app
from amaris_cms.telemetry import flush_traces, trace_operation
from amaris_cms.wsgi import application  # noqa: F401
from content.services.live_classes import process_live_class_notification

published = {}
observed = {}


@before_task_publish.connect(weak=False)
def capture_headers(headers=None, **_kwargs):
    published.update(headers or {})


@celery_app.task(name="content.tasks.telemetry_test")
def synthetic_task(_private_argument):
    observed["consumer_trace"] = format(trace.get_current_span().get_span_context().trace_id, "032x")
    raise ValueError("synthetic-private-exception@example.invalid")


@trace_operation("booking.checkout")
def synthetic_view(_request, _private_id):
    observed["web_trace"] = format(trace.get_current_span().get_span_context().trace_id, "032x")
    synthetic_task.apply_async(args=["synthetic-private-argument@example.invalid"])
    # Consume the published trace headers with real Celery task execution signals.
    # A separate broker/worker is exercised by the optional live staging check.
    synthetic_task.apply(args=["synthetic-private-argument@example.invalid"], headers=dict(published), throw=False)
    process_live_class_notification({}, gateway=None)
    return JsonResponse({"ok": True})


urls = types.ModuleType("synthetic_telemetry_urls")
urls.urlpatterns = [path("synthetic/<str:_private_id>/", synthetic_view)]
settings.ROOT_URLCONF = urls
settings.ALLOWED_HOSTS = ["testserver"]
settings.SECURE_SSL_REDIRECT = False
response = Client().get(
    "/synthetic/synthetic-private-path/?token=synthetic-private-query",
    HTTP_AUTHORIZATION="Bearer synthetic-private-authorization",
    HTTP_COOKIE="private=synthetic-private-cookie",
    HTTP_BAGGAGE="email=synthetic-private-baggage@example.invalid",
    HTTP_TRACEPARENT="00-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
    HTTP_TRACESTATE="test=synthetic-private-state",
)
assert response.status_code == 200
assert observed["consumer_trace"] == observed["web_trace"]
assert "traceparent" in published and "baggage" not in published
assert flush_traces()
print(json.dumps(observed))
