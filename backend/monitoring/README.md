# Dedicated monitoring host

This stack runs separately from the Render application. It starts Flower,
Prometheus, Grafana, cAdvisor, Alertmanager, PostgreSQL/Redis exporters, node
exporter and blackbox exporter. Caddy provides HTTPS and a password gate for the
five UI routes. No database, Redis, Celery worker, migration or application web
service is created here.

## Host and connections

Use a Linux Docker server with Docker Engine and Compose v2, a monitoring domain
pointing to that server, and inbound TCP 80/443 for HTTPS certificate issuance.
Reserve disk space for metrics and take backups of named volumes. The Prometheus,
Grafana, Flower and Alertmanager volumes survive container recreation.

The server needs authenticated, TLS connections to the existing Celery broker,
Redis cache and PostgreSQL. Render private DNS addresses are not reachable from
an external Docker server. Use the services' external addresses and allow only
the monitoring server's IP, or use an approved private-network connection. Use a
PostgreSQL monitoring account with `pg_monitor`; do not use database-owner
credentials for the exporter. Secrets are files under `secrets/`, excluded from
Git. Files must be readable by the containers' users; Docker Compose file-based
secrets are bind mounts, so keep the host directory restricted and the mounted
files readable by the relevant container UID (exporters commonly use 65534).

cAdvisor and node exporter observe **this Docker server**, not Render's managed
host. cAdvisor runs privileged with host mounts because it needs container/cgroup
access. It is only reachable on the internal monitoring network and the protected
gateway route. Alertmanager and all exporters have no public ports. Alertmanager is reachable only through its protected gateway route.

## Configure

Copy `.env.example` to `.env`. Set the real monitoring domain and the actual
HTTPS application URLs. Set reachable database/broker/cache addresses. Keep
passwords out of `.env` except the bcrypt gateway hash.

Create these secret files without committing them:

| File | Contents |
| --- | --- |
| `secrets/broker_url` | Full TLS Celery broker URI, including its credentials |
| `secrets/flower_basic_auth` | `MONITORING_USERNAME:gateway-password` |
| `secrets/grafana_admin_password` | Strong, separate Grafana admin password |
| `secrets/alertmanager_webhook_url` | Actual on-call webhook URL |
| `secrets/postgres_user` | PostgreSQL monitoring username |
| `secrets/postgres_password` | PostgreSQL monitoring password |
| `secrets/redis_broker_passwords.json` | JSON map of `REDIS_BROKER_METRICS_ADDR` to its password |
| `secrets/redis_cache_passwords.json` | JSON map of `REDIS_CACHE_METRICS_ADDR` to its password |

Redis password files use this format; the address must match the configured
exporter address exactly:

```json
{"rediss://your-redis-host:6379": "your-redis-password"}
```

Generate the gateway hash interactively:

```sh
docker run --rm -it caddy:2.10.2-alpine caddy hash-password
```

Store the resulting hash in `MONITORING_PASSWORD_HASH` in `.env`, enclosed in
single quotes. **Flower must use the same username/password as the gateway**, so
one browser Basic Auth header satisfies both checks. Grafana keeps its own login;
the gateway removes its Basic Auth header before proxying to Grafana.

## Start and verify

From this directory:

```sh
docker compose --env-file .env -f compose.yml config --quiet
docker compose --env-file .env -f compose.yml up -d
docker compose --env-file .env -f compose.yml ps
```

Check the logs for startup failures. Open all five UI URLs and confirm that an
unauthenticated request receives 401, and a valid gateway login reaches the
console. In Prometheus, check **Status → Targets**: the Django, Flower, cAdvisor,
database/cache/broker, host and blackbox targets must be up. Verify the Grafana
Prometheus datasource and provisioned Platform Overview dashboard. Send a
controlled test alert to the configured receiver after choosing an appropriate
test window; deployment alone does not authorize messaging on-call recipients.

The application metrics URL must return Prometheus text, not an HTML login or
error page. If it needs authentication, configure a corresponding Prometheus
secret before enabling that scrape. No Django credentials are sent by the default
configuration.

Set `ADMIN_MONITORING_BASE_URL=https://your-monitoring-domain` on Django to configure all console buttons at once. The infrastructure buttons open five provisioned Grafana dashboards. Alternatively, set these variables on the existing Django service after HTTPS and authentication
have been verified:

```dotenv
ADMIN_FLOWER_URL=https://your-monitoring-domain/monitoring/flower/
ADMIN_PROMETHEUS_URL=https://your-monitoring-domain/monitoring/prometheus/
ADMIN_GRAFANA_URL=https://your-monitoring-domain/monitoring/grafana/
ADMIN_CADVISOR_URL=https://your-monitoring-domain/monitoring/cadvisor/
ADMIN_ALERTMANAGER_URL=https://your-monitoring-domain/monitoring/alertmanager/
```

Deploy the Django admin integration from the same reviewed release. External
console access uses the gateway credentials; the admin's Monitoring page itself
requires an active staff superuser.

Stop with `docker compose -f compose.yml stop`. Do not delete volumes during
routine upgrades. This stack has no dependency path back into production Django,
so its failure does not stop learning, checkout or the public website.
