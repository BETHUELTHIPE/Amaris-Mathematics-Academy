# Amaris Django Admin Monitoring

## What has been wired

The Django Jazzmin **Monitoring** top-menu entry opens
`/admin/monitoring/`. It is read-only, requires an **active staff
superuser**, is not indexed, and sends `Cache-Control: no-store`.

The page displays:

- Last Prometheus `up` state for the `django`, `flower` and `cadvisor` scrape jobs.
- Django HTTP requests per second and 5xx events per second over five-minute windows, if collected.
- Explicit **not configured**, **no data**, **down** and **unreachable** states rather than fabricated zeros.
- Optional HTTPS links to private/authenticated Grafana, Flower and cAdvisor browser consoles.

The page does not scrape cAdvisor directly or send secret bearer tokens to the client.

```text
Django (/metrics) --------┐
Flower (/metrics) --------┼----> Prometheus ---> Grafana dashboards
cAdvisor (:8080/metrics) -┘             |
                                      +---> Django Admin /admin/monitoring/
```

## Docker Compose (existing self-hosted stack)

`backend/docker-compose.yml` already defines Prometheus, Grafana, Flower,
cAdvisor, alertmanager and exporters. The Prometheus scrape config is
`backend/monitoring/prometheus/prometheus.yml` and Grafana provisioning is
in `backend/monitoring/grafana/`.

The `web` container is now configured to use `http://prometheus:9090`
**internally**; no public reverse-proxy route is required. The existing
NGINX configuration blocks `/metrics` and the monitoring consoles. Do not
remove those protections. The cAdvisor service only operates on a **Docker
host where /sys, the container runtime and Docker host mounts are available**.

A Grafana dashboard is available within the Docker Compose network.
To link the browser-facing Grafana/Flower services in Django Admin, expose
them through an existing **HTTPS reverse proxy with proper authentication**,
then configure their external URLs. Do not publish Grafana with anonymous
login or expose the Flower API publicly.

## Render production — actual state, not assumptions

Amaris production Django runs on **Render's managed Python web service**.
It already installs `django-prometheus` and has the `/metrics` exporter,
but Render currently has **no deployed Prometheus, Flower, Grafana or
cAdvisor service** in the connected workspace. Their values must remain
**Not configured** until provisioned and verified.

To connect:
1. Deploy a private Prometheus service with durable storage, authenticated
   monitoring access, and a scrape job for the running Django exporter.
   Render's Prometheus deployment requires a paid instance and a persistent
   disk. Do not provision it without budget approval.
2. Set the Django service's `PROMETHEUS_API_URL` to the **internal**
   Prometheus URL, e.g. `http://prometheus:9090` only if that hostname
   actually exists on the same Render private network.
3. If the private Prometheus HTTP API requires a bearer token, set
   `PROMETHEUS_API_BEARER_TOKEN` as a **Render secret**. Never prefix the
   token in the URL or commit it.
4. Deploy Celery workers/broker and a private Flower service if needed.
   Do not claim Flower is collecting worker events when workers are absent.
5. Deploy a secured Grafana instance linked to Prometheus and set
   `GRAFANA_DASHBOARD_URL` to its HTTPS, authenticated dashboard link.
6. For cAdvisor, deploy it on a separate, explicitly managed Docker host
   with restricted host/container access and connect that host's private
   exporter to Prometheus. **Render's managed web service does not supply
   a Docker host socket.** An exporter cannot be safely assumed running
   within a Render Python web service. If no such host is available, use
   Render native CPU, memory and latency metrics separately and keep
   `cadvisor` unconfigured.

Optional link environment variables, all without inline credentials:

| Name | Purpose |
|---|---|
| `PROMETHEUS_API_URL` | Server-to-server base URL, private when possible |
| `PROMETHEUS_API_BEARER_TOKEN` | Optional server-side auth token (secret) |
| `GRAFANA_DASHBOARD_URL` | HTTPS, auth-protected browser link |
| `FLOWER_DASHBOARD_URL` | HTTPS, auth-protected browser link |
| `CADVISOR_DASHBOARD_URL` | HTTPS, auth-protected browser link on a Docker host |

## Acceptance checklist

- Admin monitoring page redirects anonymous users to Django Admin login.
- Regular staff and tutors receive HTTP 403; Django superusers receive HTTP 200.
- No credentials, internal Prometheus origin or server errors appear in the HTML.
- When no collector is configured, dashboard says **Not configured**.
- When collector is down, dashboard says **Unreachable** without slowing the
  request more than a small bounded timeout.
- With Prometheus running, the `django`, `flower` and `cadvisor` job
  states match its live `up` samples, and requests/5xx rates use actual
  collected values.
- Grafana loads its provisioned Amaris dashboard with auth, non-anonymous.
- Verify both normal browser and narrow/mobile admin views; do not embed
  Grafana in an iframe or disable `X_FRAME_OPTIONS` to make that work.
- Do not promote the release until normal Django, security, CI and production
  health gates have passed, and the production merge is approved.

**Data minimization:** metrics must not include emails, student IDs, PayFast
secrets, bearer tokens, private Zoom URLs or raw request bodies.
