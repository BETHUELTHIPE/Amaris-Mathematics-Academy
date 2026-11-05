import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult
from opentelemetry.trace import SpanKind, Status, StatusCode

from amaris_cms.telemetry import (
    PrivacyExporter,
    export_endpoint,
    initialize_tracing,
    sanitize_span,
    trace_operation,
    trace_resource,
)

BACKEND = Path(__file__).resolve().parents[1]
SAFE_RESOURCE = Resource({"service.name": "amaris-web", "deployment.environment.name": "test"})


class TelemetryTests(TestCase):
    def test_exporter_strips_names_events_resources_and_sensitive_attributes(self):
        raw = ReadableSpan(
            name="SELECT * FROM student WHERE email='private@example.invalid'",
            resource=Resource({"private": "private@example.invalid"}),
            attributes={
                "http.url": "https://example.invalid/?otp=123456",
                "http.request.header.authorization": "Bearer private",
                "db.system": "postgresql",
                "db.statement": "private@example.invalid",
                "db.operation": "SELECT",
                "messaging.message.id": "private-id",
                "enduser.id": "private-student",
            },
            events=[Event("exception", attributes={"exception.message": "private@example.invalid"})],
            status=Status(StatusCode.ERROR, "private@example.invalid"),
        )
        delegate = Mock()
        delegate.export.return_value = SpanExportResult.SUCCESS
        self.assertEqual(PrivacyExporter(delegate, SAFE_RESOURCE).export([raw]), SpanExportResult.SUCCESS)
        clean = delegate.export.call_args.args[0][0]
        self.assertEqual(clean.name, "postgresql SELECT")
        self.assertEqual(dict(clean.attributes), {"db.system.name": "postgresql", "db.operation.name": "SELECT"})
        self.assertEqual(dict(clean.resource.attributes), dict(SAFE_RESOURCE.attributes))
        self.assertEqual(clean.events, ())
        self.assertEqual(clean.links, ())
        self.assertIsNone(clean.status.description)
        self.assertEqual(clean.status.status_code, StatusCode.ERROR)

    def test_only_valid_methods_and_status_codes_are_exported(self):
        for method, code, expected in [
            ("POST", 201, "HTTP POST"),
            ("private@example.invalid", "secret", "HTTP request"),
        ]:
            span = ReadableSpan(
                "/student/private-id",
                kind=SpanKind.SERVER,
                attributes={"http.method": method, "http.status_code": code},
            )
            clean = sanitize_span(span, SAFE_RESOURCE)
            self.assertEqual(clean.name, expected)
            self.assertNotIn("private", str(clean.attributes))

    def test_unknown_names_and_task_identifiers_are_removed(self):
        for name in ["/private/student-id", "run/private@example.invalid", "redis GET private-student"]:
            self.assertEqual(sanitize_span(ReadableSpan(name), SAFE_RESOURCE).name, "dependency")
        task = "run/content.tasks.deliver_live_class_confirmation"
        self.assertEqual(sanitize_span(ReadableSpan(task), SAFE_RESOURCE).name, task)

    def test_export_errors_do_not_escape(self):
        delegate = Mock()
        delegate.export.side_effect = RuntimeError("private transport failure")
        with self.assertLogs("amaris_cms.telemetry", level="WARNING") as logs:
            self.assertEqual(
                PrivacyExporter(delegate, SAFE_RESOURCE).export([ReadableSpan("invoice.render")]),
                SpanExportResult.FAILURE,
            )
        self.assertNotIn("private transport failure", str(logs.output))

    @patch.dict(os.environ, {"AMARIS_OTEL_ENABLED": "false"})
    def test_disabled_bootstrap_creates_no_exporter(self):
        with patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter") as exporter:
            self.assertFalse(initialize_tracing())
            exporter.assert_not_called()

    @patch.dict(os.environ, {"AMARIS_OTEL_ENABLED": "true", "AMARIS_OTEL_SAMPLE_RATIO": "not-a-number"})
    def test_bad_configuration_does_not_stop_application(self):
        with self.assertLogs("amaris_cms.telemetry", level="WARNING"):
            self.assertFalse(initialize_tracing())

    def test_transport_requires_tls_by_default(self):
        with patch.dict(
            os.environ,
            {
                "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "http://jaeger:4318/v1/traces",
                "AMARIS_OTEL_ALLOW_INSECURE": "false",
            },
        ):
            with self.assertRaises(ValueError):
                export_endpoint()

    def test_endpoint_rejects_embedded_credentials_queries_and_wrong_paths(self):
        for endpoint in [
            "https://user:secret@collector/v1/traces",
            "https://collector/v1/traces?secret=x",
            "https://collector/",
            "file:///v1/traces",
        ]:
            with (
                self.subTest(endpoint=endpoint),
                patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": endpoint}),
            ):
                with self.assertRaises(ValueError):
                    export_endpoint()

    def test_resource_ignores_arbitrary_environment_attributes(self):
        with patch.dict(
            os.environ,
            {
                "OTEL_RESOURCE_ATTRIBUTES": "email=private@example.invalid",
                "OTEL_DEPLOYMENT_ENVIRONMENT": "test",
                "RELEASE_GIT_SHA": "a" * 40,
                "RENDER_GIT_COMMIT": "",
            },
        ):
            self.assertEqual(
                dict(trace_resource("web").attributes),
                {"service.name": "amaris-web", "deployment.environment.name": "test", "service.version": "a" * 40},
            )

    def test_resource_rejects_unknown_roles(self):
        with self.assertRaises(ValueError):
            trace_resource("private@example.invalid")

    def test_operation_names_are_allowlisted(self):
        with self.assertRaises(ValueError):
            trace_operation("student.private@example.invalid")

    def test_disabled_operation_preserves_return_and_exception(self):
        @trace_operation("invoice.render")
        def call(value):
            if value == "fail":
                raise ValueError("unchanged")
            return value

        self.assertEqual(call("ok"), "ok")
        with self.assertRaisesRegex(ValueError, "unchanged"):
            call("fail")

    def test_real_otlp_payload_and_web_to_celery_propagation(self):
        payloads = []

        class Receiver(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                payloads.append(self.rfile.read(int(self.headers["Content-Length"])))
                self.send_response(200)
                self.send_header("Content-Type", "application/x-protobuf")
                self.end_headers()

        server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        environment = {
            **os.environ,
            "PYTHONPATH": str(BACKEND),
            "DJANGO_DEBUG": "true",
            "DJANGO_SETTINGS_MODULE": "amaris_cms.settings",
            "DATABASE_URL": "sqlite:///:memory:",
            "SUPABASE_DATABASE_REQUIRED": "false",
            "CELERY_BROKER_URL": "memory://",
            "CELERY_RESULT_BACKEND": "cache+memory://",
            "AMARIS_OTEL_ENABLED": "true",
            "AMARIS_OTEL_SAMPLE_RATIO": "1",
            "AMARIS_OTEL_ALLOW_INSECURE": "true",
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": f"http://127.0.0.1:{server.server_port}/v1/traces",
            "OTEL_DEPLOYMENT_ENVIRONMENT": "test",
            "OTEL_RESOURCE_ATTRIBUTES": "email=synthetic-private-resource@example.invalid",
        }
        try:
            result = subprocess.run(
                [sys.executable, str(BACKEND / "tests/telemetry_scenario.py")],
                env=environment,
                cwd=BACKEND,
                capture_output=True,
                text=True,
                timeout=30,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        observed = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(observed["web_trace"], observed["consumer_trace"])
        self.assertTrue(payloads)
        spans = []
        for payload in payloads:
            self.assertNotIn(b"synthetic-private", payload)
            message = ExportTraceServiceRequest.FromString(payload)
            spans.extend(
                span for resource in message.resource_spans for scope in resource.scope_spans for span in scope.spans
            )
        names = {span.name for span in spans}
        self.assertTrue(
            {
                "HTTP GET",
                "booking.checkout",
                "booking.payment_callback",
                "apply_async/content.tasks.telemetry_test",
                "run/content.tasks.telemetry_test",
            }.issubset(names),
            names,
        )
        workflow = [
            span
            for span in spans
            if span.name
            in {
                "HTTP GET",
                "booking.checkout",
                "apply_async/content.tasks.telemetry_test",
                "run/content.tasks.telemetry_test",
            }
        ]
        self.assertEqual(len({span.trace_id for span in workflow}), 1)
        self.assertTrue(all(not span.events and not span.status.message for span in spans))
