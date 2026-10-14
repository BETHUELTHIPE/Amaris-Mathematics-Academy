# Separate self-hosted monitoring

This Compose project runs Prometheus, Grafana, Flower and cAdvisor on an existing
Linux Docker server. Caddy terminates HTTPS and NGINX checks an active Django
superuser session on every console request. No application, database, Redis,
Celery worker, migration or Render service is started by this file.

## Requirements

- Existing Linux Docker Engine server with Compose v2 and a DNS name pointing to
  it. Open TCP 80/443 and UDP 443 for Caddy. No other published monitoring ports.
- The server must reach the current Django HTTPS origin and the existing Celery
  broker using TLS and appropriate IP restrictions or a private network. Render
  private hostnames cannot be reached from an unrelated Docker host.
- Allow space for named volumes and backups. Prometheus defaults to 15 days and a
  5 GB retention limit; leave additional disk space for WAL/compaction and the
  other services. cAdvisor requires rootful Docker, cgroup access, privileged mode
  and host mounts. It measures this server, not Render's managed host.
- Celery workers must emit events (`--events`) to the existing broker. Flower
  does not create workers and cannot collect events from an absent broker.

## Configure

Copy `.env.example` to `.env`. Set `MONITORING_DOMAIN` to the real DNS hostname
and `DJANGO_ORIGIN` to the current Django HTTPS origin (no path or credentials).
Create a restricted `secrets/` directory; it is excluded from Git. Generate three
different random values using `python -c 'import secrets; print(secrets.token_urlsafe(48))'`
in your own secure terminal and put them directly in the files below, without
quotes or variable names. Do not paste secrets into issues or PRs.

| Secret file | Contents |
|---|---|
| `secrets/django_metrics_token` | Random scrape token; same as Django `MONITORING_METRICS_TOKEN` |
| `secrets/prometheus_api_token` | Different random query token; same as Django `PROMETHEUS_API_BEARER_TOKEN` |
| `secrets/grafana_admin_password` | Different strong bootstrap password; browser access uses Viewer identity |
| `secrets/broker_url` | Actual reachable TLS broker URI, including its credentials |

The API token must have 43–128 URL-safe characters. Secrets mounted into non-root
containers need readable files: keep the host `secrets/` directory at mode 0700
and the mounted files at mode 0444. Compose file secrets are bind mounts, not an
encrypted secret vault. Protect the host and its backups. Never print generated
`gateway.conf`: it contains the private query token and is written mode 0600.

Configure Django through its private environment manager, preserving existing
trusted origins:

```dotenv
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-existing-origin,https://monitoring.example.com
MONITORING_METRICS_TOKEN=<same value as django_metrics_token>
PROMETHEUS_API_URL=https://monitoring.example.com/monitoring-api
PROMETHEUS_API_BEARER_TOKEN=<same value as prometheus_api_token>
PROMETHEUS_DASHBOARD_URL=https://monitoring.example.com/monitoring/prometheus/
GRAFANA_DASHBOARD_URL=https://monitoring.example.com/monitoring/grafana/
FLOWER_DASHBOARD_URL=https://monitoring.example.com/monitoring/flower/
CADVISOR_DASHBOARD_URL=https://monitoring.example.com/monitoring/cadvisor/
```

Keep Django in production mode with secure host-only cookies. Do not configure
`SESSION_COOKIE_DOMAIN` or `CSRF_COOKIE_DOMAIN` to a shared domain. The gateway
proxies only Admin login/logout/monitoring and static assets to the existing
Django service. Django sees its own upstream Host; adding the monitoring domain
to `ALLOWED_HOSTS` is unnecessary. Add the monitoring HTTPS origin to CSRF trusted
origins so the real Django login and logout POSTs remain protected.

Review and deploy the Django integration first. Without it the gateway denies
console access. Set the scrape token before switching existing Prometheus
scrapers to the now-protected `/metrics` endpoint.

## Start and verify

From this directory, on the selected server:

```sh
docker compose --env-file .env -f compose.yml config --quiet
docker compose --env-file .env -f compose.yml up -d
docker compose --env-file .env -f compose.yml ps
```

Open `https://monitoring.example.com/admin/monitoring/` and sign in with your
Django superuser. You must sign in again on this domain; the production domain's
host-only cookie is intentionally separate. Open all four console buttons.
Grafana provisions **Amaris Self-hosted Monitoring** with Django/Flower/cAdvisor
scrape status, HTTP rates, container CPU and memory. This focused stack scrapes
only Django, Flower, cAdvisor and Prometheus. Missing series stay empty; do not
interpret them as zero or successful checks.

Verify:

1. Prometheus **Status → Targets** shows the four real targets up, including the
   authenticated Django scrape. Grafana's datasource queries work.
2. Anonymous console requests go to Django login. Student/tutor/staff requests
   return 403. Test nested API/metrics URLs as well as the landing pages.
3. Logging out, disabling the user or removing superuser status closes console
   access. Unavailable Django authentication must fail closed.
4. Query/scrape credentials cannot open consoles. Unauthenticated public metrics
   return 401, and console processes receive no Django session cookies.
5. Render learning, booking and payment pages remain healthy. Make no live charges.

No live acceptance has been performed merely by committing these files.

## Operation and rollback

Back up named volumes using a consistent snapshot or stop the relevant service
before copying data. Do not delete volumes during upgrades. When changing `.env`
or the gateway token, rerun `config` with `--force-recreate` and restart `gateway`;
configuration files are generated at initialization. For broker/scrape secret
rotation, recreate affected services too. Keep the Django token values in sync.

Stop only this monitoring project with `docker compose -f compose.yml stop`.
Clear Django console/API URL variables to show disconnected states. Restore the
previous reviewed images/configuration for rollback and retain volumes. A
monitoring outage leaves Render application services running; console access is
unavailable if Django itself is unavailable. This project provisions no paid
resources. Host, domain, storage and network availability still need verification.
