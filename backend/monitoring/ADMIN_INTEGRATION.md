# Amaris monitoring inside Django Admin

Django Admin entry: **/admin/monitoring/**. Only active Django superusers can see or proxy dashboards. No direct public dashboard port should be published.

## Current production on Render (verified 20 October 2026)

- The production Django backend is on Render in Frankfurt.
- Private `amaris-monitoring-flower:10000` is live and connected to the production Redis broker. Render logs have Celery worker-inspection warnings, so task/worker completeness is not confirmed.
- Private `amaris-monitoring-render-metrics:10000` is live; Render API HTTP-latency requests have returned 400, so its measurements must show **degraded** unless a fresh successful refresh is observed. The separate exporter fix is in PR #301.
- **No Render Prometheus or Grafana service exists in the connected workspace.** Their Django Admin tiles display **unconfigured**, not fictitious graphs or status. Creating new paid private services or persistent disks requires separate explicit cost approval.

### Connect the existing private Render services

After PR #300 passes CI and the production backend deploys, set only these nonsecret merged environment variables on `amaris-production-web`:

```text
MONITORING_CONSOLE_ENABLED=true
MONITORING_FLOWER_URL=http://amaris-monitoring-flower:10000
MONITORING_RENDER_EXPORTER_URL=http://amaris-monitoring-render-metrics:10000
```

Keep `MONITORING_GRAFANA_URL` and `MONITORING_PROMETHEUS_URL` empty until actual private services exist. Do **not** point them to public URLs or use imaginary domain names. Verify the status tiles using a real Django superuser session, then test staff/student access is forbidden.

### Docker-hosted full stack (when a Docker host exists)

`backend/docker-compose.yml` already includes **Grafana, Prometheus, Flower and cAdvisor**. Django's `web` service can reach the private Docker monitoring network. No monitoring service exposes a public dashboard port. The Docker configuration uses these internal base URLs:

```text
MONITORING_CONSOLE_ENABLED=true
MONITORING_GRAFANA_URL=http://grafana:3000
MONITORING_PROMETHEUS_URL=http://prometheus:9090
MONITORING_FLOWER_URL=http://flower:5555
```

Flower's internal basic-auth secret is in `flower_basic_auth` (username:password). Set `MONITORING_FLOWER_BASIC_AUTH` on the Django web service with the **same secret** through secure environment configuration, never commit it. Keep the Django admin HTTPS browser origin in the Docker compose environment:

```text
MONITORING_GRAFANA_BROWSER_URL=https://your-django-admin-host/admin/monitoring/grafana/
MONITORING_PROMETHEUS_BROWSER_URL=https://your-django-admin-host/admin/monitoring/prometheus/
```

The Docker profile's Grafana is internal-only with anonymous **Viewer** mode for the authenticated Django proxy. Its write/admin functions remain protected; proxy permits only GET. Docker Compose does not automatically install or run anything in the current Render production environment.

### Validation before calling the integration complete

1. Superuser sees the monitoring page; staff and students get denied.
2. Real service HTTP health probes show reachability per tool; errors/stale exporter samples show unavailable or degraded.
3. Prometheus's `up` targets for Django, Flower and itself must be 1 when the server exists.
4. Grafana datasource/graphs must show real Prometheus samples, not placeholders.
5. Flower needs real active Celery workers; a reachable console by itself does not prove the workers are operating.
6. On a Docker host, cAdvisor measures that host's actual containers. **It does not measure Render-managed host resources.**
7. Avoid putting session identifiers, emails, payment references or student data in monitoring labels.

Avoid provisioning paid Render monitoring services or disks without explicit budget approval.
