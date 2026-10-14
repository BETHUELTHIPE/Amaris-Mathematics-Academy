# Django Admin monitoring

The Jazzmin **Monitoring** entry opens `/admin/monitoring/` for active Django
staff superusers. Students, tutors and ordinary staff cannot read it. Actual
Prometheus samples supply status and throughput. Missing collectors display
**Not configured**, **No data** or **Unreachable** rather than invented metrics.

## Separate Docker server

Use [`../monitoring/self-hosted/README.md`](../monitoring/self-hosted/README.md)
for the independent Prometheus, Grafana, Flower and cAdvisor stack. It uses
persistent volumes and one HTTPS gateway. Each console request, including APIs
and nested URLs, checks the current Django session through
`/admin/monitoring/access/`. Invalid sessions cannot open consoles; disabling a
user or revoking superuser access takes effect on the next request. Auth failure
or an unavailable Django backend denies console access.

This stack starts no application services and performs no migrations. Render
services and paid resources are not provisioned by it. cAdvisor measures its
Docker host, not Render's managed infrastructure. The software has no licence
fee; the server, storage, power and internet still need to exist.

Console access requires signing into Django Admin on the monitoring domain.
Cookies remain host-only; no parent-domain sharing is needed. Keep Django's
CSRF middleware, secure cookies and HTTPS checks enabled. The setup guide lists
the required trusted origin and private environment values.

Grafana uses a gateway-injected Viewer identity after the superuser check. It
has no anonymous access, public signup or bypass login. Flower, Prometheus and
cAdvisor browser routes allow GET/HEAD only. Grafana POST requests require the
exact monitoring origin; its Viewer role protects administrative changes. Django
cookies and browser Authorization headers are removed before proxying consoles.
Only TLS publishes host ports. Do not add `ports` to collectors or exporters.

## Scrapes and Admin summaries

`/metrics` and `/metrics/` require `MONITORING_METRICS_TOKEN`. Missing or incorrect
credentials return 401, including for logged-in users. Use a strong independent
random token and copy it into the scraper's `django_metrics_token` secret file.
The existing colocated `backend/docker-compose.yml` also mounts that secret in
Prometheus. Its NGINX continues to block public `/metrics` and console routes.

The separate host exposes only Prometheus's instant query API to Django, using
a second token. `PROMETHEUS_API_URL=https://monitoring.example.com/monitoring-api`
and `PROMETHEUS_API_BEARER_TOKEN` configure server-side queries. A scrape or query
token never authorizes a browser console or acts as a Django login. Tokens,
private targets and exception details do not appear in the Admin page.

Browser links use HTTPS URLs without credentials:

| Environment variable | Destination |
|---|---|
| `PROMETHEUS_DASHBOARD_URL` | `/monitoring/prometheus/` on the monitoring domain |
| `GRAFANA_DASHBOARD_URL` | `/monitoring/grafana/` on the monitoring domain |
| `FLOWER_DASHBOARD_URL` | `/monitoring/flower/` on the monitoring domain |
| `CADVISOR_DASHBOARD_URL` | `/monitoring/cadvisor/` on the monitoring domain |

## Release checks

Run Django authorization and health tests plus
`python monitoring/self-hosted/test_gateway.py` with NGINX available. The gateway
checks exercise actual NGINX requests against synthetic auth and console
upstreams. The separate CI workflow also validates Compose and Prometheus
configuration. Run live acceptance on the chosen Docker host before claiming
that telemetry is connected: all scrape targets up, Grafana datasource working,
every console blocked for anonymous/student/tutor/staff sessions, and access
revocation effective. Verify production health after the reviewed Django release.

Metrics must not include student identifiers, private Zoom links, payment secrets
or request bodies. Flower can contain sensitive task arguments/results: restrict
its retention and never pass private student data in task payloads unnecessarily.
