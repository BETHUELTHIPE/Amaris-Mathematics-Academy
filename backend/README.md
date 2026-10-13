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

Open **Monitoring** from the Django admin top menu or home page. The five consoles open in new tabs, and the Monitoring page is restricted to active staff superusers. Docker routes every console request through a Django session check, including assets, API calls and Grafana WebSocket upgrades. Signing out of Django removes access through these routes. Flower's basic authentication and Grafana's own login remain enabled.

- Flower: `http://localhost:8080/monitoring/flower/`
- Prometheus: `http://localhost:8080/monitoring/prometheus/`
- Grafana: `http://localhost:8080/monitoring/grafana/`
- cAdvisor: `http://localhost:8080/monitoring/cadvisor/`
- Alertmanager: `http://localhost:8080/monitoring/alertmanager/`

Monitoring container ports and Django's metrics endpoint remain private; pgAdmin is not exposed. Prometheus continues scraping directly over Docker's private networks, with updated paths for the Prometheus and cAdvisor prefixes. Flower is defined exactly once and is the operational interface for Celery Worker and Celery Beat monitoring. `FLOWER_PORT` remains `5555`, `FLOWER_URL` is the internal `http://flower:5555` address, and `FLOWER_BASIC_AUTH` must contain a strong `username:password` value. Docker passes that credential as a runtime secret; it is not stored in Prometheus configuration or source control.

Grafana listens internally on `GRAFANA_PORT=3000` at `GRAFANA_URL=http://grafana:3000`. Configure `GF_SECURITY_ADMIN_USER`, a strong `GF_SECURITY_ADMIN_PASSWORD`, and keep `GF_USERS_ALLOW_SIGN_UP=false`. The admin password is passed with Grafana's file-based secret setting and is not exposed directly in the container environment. Set `GF_SERVER_ROOT_URL` and `PROMETHEUS_EXTERNAL_URL` to the actual public HTTPS origin followed by `/monitoring/grafana/` and `/monitoring/prometheus/` respectively. Keep these path prefixes; enable secure Grafana cookies in production. The proxy expects Flower on port 5555 and Grafana on port 3000.

For one monitoring host, set `ADMIN_MONITORING_BASE_URL=https://your-monitoring-domain`. This configures all five console buttons automatically; individual `ADMIN_*_URL` settings override a console address. The Monitoring page also links to provisioned Grafana dashboards for PostgreSQL, the Redis broker/cache, Docker host and uptime.

Docker enables `ADMIN_MONITORING_PROXY_ENABLED=true` for the web container. Standalone Django/Render deployments default to no proxy and display “Connection not configured” until browser URLs are supplied:

```dotenv
ADMIN_FLOWER_URL=https://your-authenticated-flower-host/monitoring/flower/
ADMIN_PROMETHEUS_URL=https://your-authenticated-prometheus-host/
ADMIN_GRAFANA_URL=https://your-grafana-host/
ADMIN_CADVISOR_URL=https://your-authenticated-cadvisor-host/
ADMIN_ALERTMANAGER_URL=https://your-authenticated-alertmanager-host/
```

External links use each console host's own access controls; Django's session cannot protect a different host. Supply HTTP(S) URLs without embedded passwords. Do not use private Docker DNS names such as `http://grafana:3000` as browser links. No monitoring services are provisioned by these settings. cAdvisor needs access to the Docker host and its metrics cannot be obtained from a managed Render web container without a suitable separate monitoring host.

For a dedicated Docker monitoring server alongside the Render app, use [`monitoring/compose.yml`](monitoring/compose.yml) and the [host deployment guide](monitoring/README.md). This starts all monitoring services without starting or migrating a second copy of Django, PostgreSQL or Redis.

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

Django + Flower + cAdvisor -> Prometheus -> Grafana
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
