# Self-hosted, Django-superuser-only monitoring

This deployment uses the **existing** open-source Docker images for Prometheus, Grafana, Flower,
cAdvisor, exporters and Alertmanager. No Render monitoring services, disks or workers are created.

## Two distinct deployment locations

- **Self-hosted Compose:** Django, Nginx and monitoring containers share the internal Docker
  network. The private monitoring gateway works from this Django Admin.
- **Existing Render production:** The Django admin there runs on Render, **not** inside your
  self-hosted Docker network. Its monitoring page remains **unconfigured** by default. A
  private VPN/tunnel and deliberate integration are required before its admin could reach
  the Docker services. Never point a public DNS hostname at Grafana/Flower/Prometheus
  or open their native ports to work around this.

The Docker machine can probe both public Render URLs over HTTPS, but **cannot** infer
Render worker status, process CPU, Redis queues or internal database metrics.
cAdvisor measures containers **on the Docker host only**. Flower reports only the
Celery workers using **the broker configured for that Flower instance**.
Missing sources are not presented as healthy measurements.

## Deployment on an existing Docker host

1. Install Docker Engine / Docker Compose on a computer or server **you control**.
   Keep the monitoring host patched, encrypted and reachable only over localhost or
   a trusted VPN. Docker may use disk space, electricity or hosting capacity even
   though the monitoring software is free.
2. Checkout the approved release branch and enter `backend/`.
3. Copy `.env.example` to `.env` and set normal **local/self-hosted** application
   variables. Never reuse production credentials, webhook secrets or databases for a
   trial stack. The existing Compose file also starts Celery workers, migrations,
   payment reconciliation, backups and restores. Do not run it pointed at live
   Supabase/PayFast unless those operational services have been reviewed.
4. Set `DJANGO_DEBUG=false`, `MONITORING_PUBLIC_BASE_URL=http://localhost:8080`,
   `NGINX_PORT=8080`, a strong `MONITORING_METRICS_TOKEN`, `FLOWER_BASIC_AUTH`
   (format `username:strong-password`), `GF_SECURITY_ADMIN_USER` and
   `GF_SECURITY_ADMIN_PASSWORD`, along with the existing required
   `ALERTMANAGER_WEBHOOK_URL` and backup/recovery secrets.
   Use a secrets manager or secured environment; **never commit these values**.
   When access is via HTTPS reverse proxy on a VPN, set
   `MONITORING_PUBLIC_BASE_URL` to that exact origin (no trailing slash).
5. Validate locally using `docker compose config --quiet` before starting services.
6. With local data and secrets correctly configured, run
   `docker compose up --build -d`; inspect `docker compose ps` and
   `docker compose logs --tail=100 web prometheus grafana flower cadvisor`.
7. Visit `http://localhost:8080/admin/`, sign in as an **active Django superuser**,
   and follow **Private operations monitoring -> Open monitoring dashboard**.
8. Confirm a normal staff account is forbidden from the monitoring gateway,
   and unauthenticated calls to `/metrics`, native Grafana and Flower ports
   return no sensitive data.

## Security design

- All monitoring containers run on private Docker networks with **no public ports**.
- The public Nginx entrypoint blocks `/metrics` and the old `/monitoring/*` URLs.
- Every Django `/admin/monitoring/*` request requires an authenticated,
  active, staff **superuser**, never merely a staff permission.
- The Django gateway proxies **GET-only** requests to fixed Docker DNS hostnames,
  does not forward browser cookies/Authorization, rejects redirects outside its own
  prefix, imposes response-size limits and keeps data out of caches.
- Grafana uses anonymous **Viewer** only *inside the private network*;
  this is **not a publicly exposed login**. Admin credentials remain secret.
- Flower retains its own Basic authentication. The gateway supplies the secret
  internally; browsers cannot obtain it from monitoring responses.
- Direct Django `/metrics` access in production requires
  `Authorization: Bearer <MONITORING_METRICS_TOKEN>`. Without a token, the
  endpoint returns 404. Prometheus obtains the secret using a Compose secret file.
- No unsafe cross-site iframes, administrative API writes, WebSocket bypasses,
  or direct browser links to Docker container ports are required.
- Prometheus and Grafana are configured for the
  `/admin/monitoring/{prometheus,grafana}/` URL prefixes. Grafana Live WebSocket
  streaming is not proxied; normal read-only HTTP dashboard queries are intended.

## Validation and limitations

Run `python manage.py test tests.test_monitoring_admin` in the backend's
Python environment and inspect the logs above. Verify the Grafana dashboard
shows real `up` and probe samples. If an exporter is not reachable its
Prometheus target is down/unavailable, not silently shown as passing.

Do not expose the self-hosted Nginx HTTP listener publicly. Compose binds it
to `127.0.0.1` by default. To use a separate computer, connect through a
trusted VPN or an HTTPS reverse proxy with tight ingress restrictions and
strong Django authentication. Do not port-forward native monitoring services.

If and only if a secure private connection from the **Render** backend to this
monitoring host is subsequently provided, the Django gateway can be integrated
on Render with new deployment-specific, authenticated private routing. That
connectivity is not provisioned here; the Render page must remain unconfigured
until separately tested and approved.

## Reversal

The existing Render production services are unchanged. Stop the local
self-hosted stack via `docker compose down` (without `-v`, preserving data).
Disable the admin feature with `MONITORING_CONSOLE_ENABLED=false`.
