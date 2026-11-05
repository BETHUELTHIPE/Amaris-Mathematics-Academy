"""Opt-in, bounded tracing. Only allowlisted metadata crosses the exporter boundary.

Do not enable generic ``opentelemetry-instrument`` alongside this bootstrap. Raw
instrumentor spans can contain SQL, URLs and exception messages; the sanitizing
exporter is deliberately the only path from the SDK to the network.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable, Sequence
from functools import wraps
from typing import ParamSpec, TypeVar
from urllib.parse import urlsplit

from opentelemetry import propagate, trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, SpanLimits, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import SpanContext, SpanKind, Status, StatusCode, TraceState
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

LOGGER = logging.getLogger(__name__)
P = ParamSpec("P")
R = TypeVar("R")
_provider: TracerProvider | None = None
_initialized_pid: int | None = None
OPERATIONS = frozenset(
    {
        "booking.checkout",
        "booking.payment_callback",
        "video.checkout",
        "video.payment_callback",
        "course.checkout",
        "course.payment_callback",
        "invoice.render",
        "invoice.archive",
        "notification.email",
        "telemetry.canary",
    }
)
METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
DB_OPERATIONS = frozenset({"SELECT", "INSERT", "UPDATE", "DELETE", "COMMIT", "ROLLBACK", "BEGIN"})


def enabled() -> bool:
    return os.getenv("AMARIS_OTEL_ENABLED", "false").lower() == "true"


def export_endpoint() -> str:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "").strip()
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path != "/v1/traces"
    ):
        raise ValueError("Configure an OTLP HTTP traces endpoint without credentials or query parameters.")
    # Plain HTTP requires a deliberate opt-in on a trusted private network or
    # loopback/SSH tunnel. Never use this override for a public endpoint.
    if parsed.scheme == "http" and os.getenv("AMARIS_OTEL_ALLOW_INSECURE", "false").lower() != "true":
        raise ValueError("OTLP requires HTTPS unless the private-network override is explicitly enabled.")
    _ = parsed.port  # Reject invalid port numbers without logging the endpoint.
    return endpoint


def trace_resource(role: str) -> Resource:
    environment = os.getenv("OTEL_DEPLOYMENT_ENVIRONMENT", "development")
    if environment not in {"development", "test", "staging", "production"}:
        raise ValueError("Invalid telemetry deployment environment.")
    if role not in {"web", "celery", "beat", "canary"}:
        raise ValueError("Invalid telemetry service role.")
    attributes = {"service.name": f"amaris-{role}", "deployment.environment.name": environment}
    release = os.getenv("RENDER_GIT_COMMIT") or os.getenv("RELEASE_GIT_SHA") or ""
    if re.fullmatch(r"[a-fA-F0-9]{40}", release):
        attributes["service.version"] = release
    # Resource.create() and default detectors can copy arbitrary environment
    # attributes and host identifiers. Use an explicit, minimal Resource instead.
    return Resource(attributes)


def sanitize_span(span: ReadableSpan, resource: Resource) -> ReadableSpan:
    raw = span.attributes or {}
    attributes: dict[str, str | int] = {}
    method = raw.get("http.request.method", raw.get("http.method"))
    if isinstance(method, str) and method in METHODS:
        attributes["http.request.method"] = method
    code = raw.get("http.response.status_code", raw.get("http.status_code"))
    if type(code) is int and 100 <= code <= 599:
        attributes["http.response.status_code"] = code
    system = raw.get("db.system.name", raw.get("db.system"))
    if isinstance(system, str) and system in {"postgresql", "redis"}:
        attributes["db.system.name"] = str(system)
    operation = raw.get("db.operation.name", raw.get("db.operation"))
    if isinstance(operation, str) and operation in DB_OPERATIONS:
        attributes["db.operation.name"] = operation

    # No raw span names: SQL and paths can contain names, IDs or tokens.
    if span.name in OPERATIONS:
        name = span.name
    elif "db.system.name" in attributes:
        name = f"{attributes['db.system.name']} {attributes.get('db.operation.name', 'command')}"
    elif re.fullmatch(r"(?:apply_async|run)/content\.tasks\.[a-z_]{1,80}", span.name):
        name = span.name
    elif span.kind == SpanKind.SERVER:
        name = f"HTTP {attributes.get('http.request.method', 'request')}"
    else:
        name = "dependency"
    return ReadableSpan(
        name=name,
        context=_clean_context(span.context),
        parent=_clean_context(span.parent),
        resource=resource,
        attributes=attributes,
        events=(),  # Exclude exception messages, stack traces and arbitrary events.
        links=(),  # No baggage or link attributes from external callers.
        kind=span.kind,
        status=Status(span.status.status_code),  # Exclude exception descriptions.
        start_time=span.start_time,
        end_time=span.end_time,
    )


def _clean_context(context: SpanContext | None) -> SpanContext | None:
    if context is None:
        return None
    # Preserve correlation IDs, never a caller-controlled tracestate value.
    return SpanContext(context.trace_id, context.span_id, context.is_remote, context.trace_flags, TraceState())


class PrivacyExporter(SpanExporter):
    def __init__(self, delegate: SpanExporter, resource: Resource):
        self.delegate = delegate
        self.resource = resource

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            return self.delegate.export(tuple(sanitize_span(span, self.resource) for span in spans))
        except Exception:
            # Telemetry failure must not fail a booking or leak an exception.
            LOGGER.warning("Trace export failed; application processing continues.")
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        self.delegate.shutdown()


def initialize_tracing(role: str = "web") -> bool:
    global _provider, _initialized_pid
    if not enabled():
        return False
    if _initialized_pid == os.getpid():
        return True
    if not isinstance(trace.get_tracer_provider(), trace.ProxyTracerProvider):
        LOGGER.warning("Tracing startup skipped: another provider is already configured.")
        return False
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.celery import CeleryInstrumentor
        from opentelemetry.instrumentation.django import DjangoInstrumentor
        from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        ratio = float(os.getenv("AMARIS_OTEL_SAMPLE_RATIO", "0.05"))
        if not 0 <= ratio <= 1:
            raise ValueError("Telemetry sample ratio must be between zero and one.")
        resource = trace_resource(role)
        # Validate before constructing any SDK threads or instrumentation.
        exporter = OTLPSpanExporter(endpoint=export_endpoint(), timeout=2)
        provider = TracerProvider(
            resource=resource,
            sampler=ParentBased(TraceIdRatioBased(ratio)),
            span_limits=SpanLimits(max_attributes=32, max_events=0, max_links=0, max_attribute_length=256),
        )
        provider.add_span_processor(
            BatchSpanProcessor(
                PrivacyExporter(exporter, resource),
                max_queue_size=512,
                max_export_batch_size=64,
                schedule_delay_millis=5000,
                export_timeout_millis=2000,
            )
        )
        trace.set_tracer_provider(provider)
        # Trace IDs cross queues; user-controlled baggage never does.
        propagate.set_global_textmap(TraceContextTextMapPropagator())
        DjangoInstrumentor().instrument(
            tracer_provider=provider,
            excluded_urls=r"/health(?:/|$),/metrics(?:/|$),/admin(?:/|$),/static/,/media/",
        )
        CeleryInstrumentor().instrument(tracer_provider=provider)
        PsycopgInstrumentor().instrument(tracer_provider=provider, capture_parameters=False)
        RedisInstrumentor().instrument(tracer_provider=provider)
        _provider = provider
        _initialized_pid = os.getpid()
        return True
    except Exception:
        LOGGER.warning("Tracing could not start; check telemetry configuration. Application processing continues.")
        return False


def flush_traces() -> bool:
    return _provider.force_flush(timeout_millis=3000) if _provider else False


def trace_operation(operation: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    if operation not in OPERATIONS:
        raise ValueError("Telemetry operation must be allowlisted.")

    def decorate(function: Callable[P, R]) -> Callable[P, R]:
        @wraps(function)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            if _provider is None:
                return function(*args, **kwargs)
            with trace.get_tracer("amaris.workflows").start_as_current_span(
                operation, record_exception=False, set_status_on_exception=False
            ) as span:
                try:
                    return function(*args, **kwargs)
                except Exception:
                    span.set_status(Status(StatusCode.ERROR))
                    raise

        return wrapped

    return decorate
