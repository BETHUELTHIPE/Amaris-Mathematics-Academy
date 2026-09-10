# Amaris Django CMS and Jazzmin Admin

This service gives Amaris Mathematics Academy a production Django administration system while the existing Next.js website remains the public frontend. The backend is deployed separately and connected to Next.js only through `CMS_API_URL` after it has a stable HTTPS address.

## What administrators can manage

- brand, contact details, navigation and site settings
- pages and reusable page sections
- mathematics categories, courses, modules and lessons
- private YouTube references and private S3 video uploads
- worksheets, study notes, past papers and memoranda
- pricing plans, testimonials, FAQs and announcements
- enquiries, student records, enrolments and read-only payment records
- publishing status and scheduled publication

Every model in the `content` application is registered in Django Admin. Jazzmin provides the branded interface.

## Local setup

1. Copy `.env.example` to `.env` and replace every placeholder secret.
2. Run `docker compose up --build -d`.
3. Create the administrator with `docker compose exec web python manage.py createsuperuser`.
4. Load the existing Amaris catalogue with `docker compose exec web python manage.py seed_content`.
5. Open `http://localhost:8080/admin/`.

The stack also starts encrypted backup, payment-reconciliation and isolated restore-testing services. Configure the Restic repository and placeholder recovery credentials in `.env` before treating local health as production evidence. Production must set `MIGRATION_BACKUP_REQUIRED=true` so schema changes cannot begin until a pre-migration recovery point succeeds.

The public content API is available under `/api/v1/`, with interactive documentation at `/api/docs/`.

Load and resilience tests are in [`load_tests/`](load_tests/README.md). The suite covers public browsing, authentication entry points, protected student activity, progress, checkout creation and payment polling, with normal, peak, spike and controlled dependency-failure profiles. It blocks the live Amaris and PayFast hosts by default.

The monitoring interfaces are available through the same NGINX entrypoint:

- Flower: `http://localhost:8080/monitoring/flower/`
- Grafana: `http://localhost:8080/monitoring/grafana/`
- pgAdmin: `http://localhost:8080/monitoring/pgadmin/`

Prometheus and cAdvisor have no public host ports. Flower is defined exactly once and is the operational interface for Celery Worker and Celery Beat monitoring. `FLOWER_PORT` remains `5555`, `FLOWER_URL` is the internal `http://flower:5555` address, and `FLOWER_BASIC_AUTH` must contain a strong `username:password` value. Docker passes that credential as a runtime secret; it is not stored in Prometheus configuration or source control.

Grafana listens internally on `GRAFANA_PORT=3000` at `GRAFANA_URL=http://grafana:3000`. Configure `GF_SECURITY_ADMIN_USER`, a strong `GF_SECURITY_ADMIN_PASSWORD`, and keep `GF_USERS_ALLOW_SIGN_UP=false`. The admin password is passed with Grafana's file-based secret setting and is not exposed directly in the container environment.

## Runtime layout

```text
Existing public Next.js Site (unchanged)
        |
        | HTTPS CMS_API_URL
        v
NGINX -> Gunicorn + UvicornWorker -> Django / Jazzmin
                     |                 |
                     |                 +-> PostgreSQL
                     +--------------------> Redis
                                           |-> Celery Worker
                                           |-> Celery Beat
                                           +-> Flower (one instance)

Prometheus -> Django + Flower + cAdvisor -> Grafana
```

Gunicorn remains the production process manager. Its Uvicorn worker runs Django's ASGI application, so future asynchronous endpoints can be added without replacing the current HTTP deployment model.

Performance defaults are environment-driven: Gunicorn recycles workers with jitter, Django reuses healthy database connections, PostgreSQL records normalised query statistics, and public API responses use a separate eviction-safe Redis cache. Do not increase web or Celery concurrency until the resulting database connection total and container memory remain within the headroom defined in [`../docs/PERFORMANCE.md`](../docs/PERFORMANCE.md).

## AWS production notes

- Deploy `web`, `celery_worker` and `celery_beat` from the same container image to ECS/Fargate or EC2.
- Use an Application Load Balancer in front of the `web` service; use Nginx when deploying on EC2.
- Use Amazon RDS for PostgreSQL, ElastiCache for Redis and a private S3 bucket for uploads.
- Keep database, Django and AWS credentials in AWS Secrets Manager. Never commit `.env`.
- Configure CloudFront signed URLs or application-authorized S3 links before exposing paid lesson files.
- Keep full-length teaching videos private on YouTube where practical; store the video ID in Jazzmin. S3 upload remains available for controlled assets.
- Terminate HTTPS at the load balancer or production NGINX layer. Set `GF_SECURITY_COOKIE_SECURE=true` before production access.
- Set `DJANGO_DEBUG=false`, production hosts, CSRF origins, the public frontend CORS origin, HTTPS and a strong secret key.

The current Next.js site already contains the CMS adapter for its brand details, navigation, course catalogue, pricing and enquiry delivery. Give the frontend a server-side `CMS_API_URL` only after this service has a stable HTTPS production address. Until then, the public site automatically continues using its existing content and enquiry database safely.

## Reliability and disaster recovery

The production target is a **6-hour RPO** and **4-hour RTO**. PostgreSQL plus locally stored media are backed up every six hours to a client-side encrypted off-server Restic repository, retained as 7 daily, 5 weekly and 12 monthly recovery points, and restored into an isolated disposable PostgreSQL instance every week. Redis is excluded from Django readiness, Celery uses late acknowledgements and bounded retry backoff, and a Redis-independent watchdog reconciles server-verified payments with enrolments.

Full activation, restoration, Redis/Celery recovery, payment reconciliation, graceful shutdown, migration rollback and alert-response procedures are in [`docs/DISASTER_RECOVERY.md`](docs/DISASTER_RECOVERY.md).

The `Page` and `PageSection` endpoints provide the remaining editorial content for progressive migration without exposing draft material. Private video URLs and source files are intentionally excluded from public API responses; paid lesson delivery must verify the student's enrolment before issuing access.

## Error recovery

Django uses branded handlers for 400, 403, 404 and 500 errors, with a controlled 429 recovery route. `CorrelationReferenceMiddleware` attaches an opaque `X-Correlation-ID` to every Django response and makes that reference available to the safe error template. Exception messages, stack traces, secrets and infrastructure names are never rendered.

NGINX intercepts upstream 502 and 503 responses and serves the static branded pages in `nginx/errors/`. These pages do not depend on Django, PostgreSQL or Redis, so they remain available when the application server is offline. The NGINX request ID is displayed as the support reference. Keep the error directory mounted read-only in production.
