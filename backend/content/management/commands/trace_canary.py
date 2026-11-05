"""Emit a synthetic trace without reading students, bookings or credentials."""

from django.core.management.base import BaseCommand, CommandError
from opentelemetry import trace

from amaris_cms.telemetry import flush_traces, initialize_tracing


class Command(BaseCommand):
    help = "Emit a synthetic OpenTelemetry trace; verify its ID in Jaeger separately."

    def handle(self, *args, **options):
        if not initialize_tracing("canary"):
            raise CommandError("Tracing is disabled or telemetry configuration is invalid.")
        with trace.get_tracer("amaris.canary").start_as_current_span("telemetry.canary") as span:
            span_context = span.get_span_context()
            if not span.is_recording():
                raise CommandError("Canary was not sampled. Use AMARIS_OTEL_SAMPLE_RATIO=1 for this command only.")
            trace_id = format(span_context.trace_id, "032x")
        if not flush_traces():
            raise CommandError("Trace flush did not finish within the configured timeout.")
        self.stdout.write(f"Synthetic trace ID: {trace_id}")
        self.stdout.write("Flush completed. Ingestion is NOT VERIFIED until this ID is found in Jaeger.")
