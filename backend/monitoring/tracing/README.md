# Amaris OpenTelemetry and Jaeger

This release adds **server-side tracing**, disabled by default, to the current
`production-release-20260923` backend. It does not start services, change billing,
run migrations, or enable browser tracking. Review and test this branch in the
isolated staging environment before promoting the exact tested commit.

## Included

- Django request, Celery publish/execute, psycopg PostgreSQL and Redis spans.
- Fixed workflow spans for course/live-class/video checkout and payment callbacks,
  invoice PDF rendering/archival and live-class/video email delivery.
- W3C trace-context propagation into queued tasks. No baggage propagator.
- A single sanitizing export boundary: raw URLs, route IDs, query strings, SQL,
  Redis keys, task arguments/IDs, account fields, credentials, events, exception
  text, arbitrary resource attributes and tracestate are excluded from export.
- HTTP method/status, database system/allowlisted operation, fixed workflow/task
  names, timing, error status and correlation IDs remain available.
- Jaeger v2, with its built-in Collector pipeline and 48-hour Badger trace TTL.
  No separate Collector service is required for this initial deployment.
- A **Jaeger traces** link in Django Admin -> Monitoring. Every UI/API/static
  request passes the existing active staff-superuser check. The proxy permits
  GET only, strips browser cookies/authorization, and returns private/no-store.
  Ordinary staff, tutors, students and inactive users cannot access it.

The existing Prometheus metrics, logs and alerts remain necessary. Five-percent
head sampling does not retain every error. A trace is diagnostic evidence, not
the booking ledger or proof of payment/email delivery. A reachable console also
does not prove ingestion; verify a trace ID explicitly.

## Bootstrap and operating limits

ASGI/WSGI initializes tracing after settings/secret files load, before middleware
is built, inside each Gunicorn worker. Do not use Gunicorn `--preload` or wrap
startup with `opentelemetry-instrument`; these bypass the intended lifecycle or
privacy boundary. Celery prefork children initialize on `worker_process_init`;
solo/thread workers and Beat have dedicated startup hooks. Shutdown flushes are
bounded. Export failure does not fail a booking; bounded queues can drop traces
when the receiver is unavailable. Invalid telemetry configuration logs a generic
warning and leaves the application running.

Default parent-based sampling is 5% for root traces. Child spans honor the parent
sampling decision. Incoming trace context should be trusted only from controlled
ingress/services; apply normal ingress rate limits. SDK queue: 512 spans per
process; export batch: 64; exporter timeout: 2 seconds. Jaeger has a 512 MiB
container cap, 384 MiB memory limiter and 0.5 CPU limit. Measure overhead and disk
growth in staging before selecting production resource limits.

Badger is a **single-node, modest-volume** starting point. The 48-hour TTL is not
a hard disk quota and physical space reclamation may lag expiry. Monitor the
volume, restrict host access and keep observability separate from application
data. Larger traffic requires a measured storage/retention plan; this is not
evidence of 100,000 concurrent-user capacity.

## Existing Docker host installation

Requires a user-approved, existing Linux Docker host and deployed backend image.
Do not launch the entire application stack merely to add tracing.

1. In `backend/`, configure the existing private `.env` from the documented
   example without overwriting its current credentials. Keep tracing disabled.
2. Validate and start **only** Jaeger:

   ```sh
   docker compose --env-file .env --profile tracing config --quiet
   docker compose --env-file .env --profile tracing up -d --no-deps jaeger
   ```

   It publishes no host ports. Its named volume mounts the image's writable
   `/tmp` directory; data lives in `/tmp/amaris-jaeger/`. The rest of the container
   is read-only, runs as the image's non-root user and drops Linux capabilities.
   The backend web/workers can reach it on the existing private backend network.

3. Set these values in the backend web and notification/general worker process
   environments, then restart only the affected application processes using the
   normal staging release procedure:

   ```dotenv
   AMARIS_OTEL_ENABLED=true
   AMARIS_OTEL_SAMPLE_RATIO=0.05
   OTEL_DEPLOYMENT_ENVIRONMENT=staging
   OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://jaeger:4318/v1/traces
   AMARIS_OTEL_ALLOW_INSECURE=true
   ```

   The HTTP override is only for the trusted private network. Remote endpoints
   require verified HTTPS, optional server-held OTLP authentication headers or
   mTLS, and an authenticated receiver. Never publish the raw OTLP/query ports.

4. On Django web only, set `MONITORING_JAEGER_URL=http://jaeger:16686`. Enable
   `MONITORING_CONSOLE_ENABLED=true` only when the intended private consoles are
   configured. Open Django Admin -> Monitoring -> Jaeger traces as a superuser.
   Jaeger is configured for the exact `/admin/monitoring/jaeger` proxy prefix.

## Render installation boundary

Docker Compose is not executed by Render. Render applications need a reachable
private Jaeger service with a persistent disk, or a separately hosted secure OTLP
receiver. The existing Render connector reports the Amaris application and
monitoring services suspended for billing; no Jaeger service exists there.
Creating another paid service, resuming billing-suspended services, and opening
public receiver ports are not part of this code change. Do not point Render at a
Docker-only hostname or assume a monitoring link means the backend exists.

Next.js/Vinext server tracing and frontend-to-Django propagation are not added in
this backend release. Existing browser Web Vitals are a separate measurement.

## Acceptance and rollback

1. Run the dedicated `OpenTelemetry and Jaeger` workflow and the existing release
   gates. It validates the exact Jaeger configuration and tests ingestion and
   Badger persistence across a process restart. Full Docker runtime authorization,
   staging worker/broker processing and production overhead still require the
   actual deployment environment.
2. Emit only a synthetic canary from the target backend environment:

   ```sh
   AMARIS_OTEL_SAMPLE_RATIO=1 python manage.py trace_canary
   ```

   Find its printed ID in Jaeger. Flush completion alone is not ingestion proof.
   Restore the normal sample ratio; the command-line override changes this
   command only. The canary reads no student records and sends no notifications.
3. In staging, use approved synthetic booking fixtures to verify request ->
   queued task -> invoice spans, error statuses and dependency timing. Inspect
   exported traces for private data; test superuser access, logged-out/student/
   tutor/staff denial, static assets and API requests through the Django proxy.
4. Observe CPU, memory, p95 latency, worker throughput and trace volume under a
   controlled load. Test receiver outage/recovery and disk/restart behavior.
5. Rollback: set `AMARIS_OTEL_ENABLED=false` and restart affected application
   processes. Remove `MONITORING_JAEGER_URL` to disable its link. Stop only the
   `jaeger` service if needed. Retain its volume until reviewed; never run
   `docker compose down -v` against the application stack. No schema rollback
   or student-data change is required.

## Local verification

```sh
python manage.py test tests.test_telemetry tests.test_monitoring_admin --noinput
python monitoring/tracing/smoke.py /absolute/path/to/jaeger
```

`--memory` may be used for the smoke test in environments without working Badger
filesystem support; it explicitly does **not** verify persistence. Tests use
synthetic data and a local OTLP receiver, including actual Django middleware and
Celery publish/execute signals. They do not claim a live broker acceptance test.
