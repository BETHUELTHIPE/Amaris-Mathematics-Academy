# Amaris Apache Airflow — opt-in operations stack

**Using only Render?** Use [the Render Docker Blueprint](render/README.md).
It replaces Compose networking and bind mounts with Render services and baked-in
DAGs. No VPS, SSH host or purchased domain is needed. Importing it provisions
additional paid resources; source preparation does not deploy anything.

This adds a separate Airflow 3 Docker deployment profile and a read-only
Django Admin monitor. It does **not** launch production resources, modify
PayFast or tutor payout logic, or change Supabase database tables.

## Included

- Airflow 3 API server, scheduler and DAG processor with LocalExecutor.
- Separate persisted PostgreSQL metadata database, never Django production DB.
- A read-only service-health DAG checking backend and live student site.
- Airflow StatsD metrics sent to a Prometheus StatsD exporter.
- Superuser-only Django Admin workflow panel: latest run and task states,
  errors and execution history; automatic 30-second refresh.
- No task execution controls or Airflow administration API exposed to tutors.

## Prerequisites and release blockers

1. An approved VPS with Docker Compose, capacity, disk and backups.
2. Production Airflow RBAC / identity-provider authentication. The Simple
   Auth Manager example is for local evaluation ONLY, never public access.
3. A secure HTTPS/TLS tunnel reachable from the Django Render backend,
   authenticated and restricted at ingress. The VPS API is bound to loopback.
4. An authenticated read-only Airflow service identity and a short-lived
   API token rotation or renewal procedure.
5. Metadata DB backup and restoration proof, observability, firewall rules,
   resource quotas, audited staging tests and controlled release approval.

## VPS preparation, after explicit approval

~~~sh
cd airflow
cp .env.example .env
chmod 600 .env
# Replace placeholder values using a secret manager.
docker compose --env-file .env -f compose.yml config --quiet
docker compose --env-file .env -f compose.yml up -d airflow-postgres statsd-exporter
docker compose --env-file .env -f compose.yml run --rm airflow-init
docker compose --env-file .env -f compose.yml up -d airflow-api airflow-scheduler airflow-dag-processor
~~~

The Airflow HTTP API binds to 127.0.0.1:8081. Never expose it unprotected.
Do not run the stack on the live Django web service.

## Django Render configuration (staging first)

Set these server-side environment variables without adding secrets to GitHub:

| Variable | Description |
| --- | --- |
| AIRFLOW_MONITORING_ENABLED | true only after secured connectivity is verified |
| AIRFLOW_API_BASE_URL | Private HTTPS URL for the Airflow API |
| AIRFLOW_API_TOKEN | Read-only service bearer token with rotation |
| AIRFLOW_MONITORED_DAGS | Comma-separated allowlist, initially amaris_service_health |

Browse /admin/airflow/ while signed in as a Django superuser. Ordinary
staff, tutors and students are denied. When configuration is incomplete or
the token expires, display unavailable rather than fabricated health.

## Prometheus and Grafana

Airflow emits StatsD to statsd-exporter:9125 over UDP on the Docker network.
Exporter metrics are at :9102. Attach a co-hosted Prometheus instance to the
Airflow network and add the job below. If Prometheus is remote on Render,
use a private authenticated metrics tunnel instead.

~~~yaml
  - job_name: airflow-statsd
    scrape_interval: 30s
    static_configs:
      - targets: ["statsd-exporter:9102"]
~~~

The dashboard expects this Prometheus job label. No-data is not healthy.
Keep Prometheus, Grafana, Flower and Celery; Airflow only observes DAGs
explicitly implemented, not every Django transaction automatically.

## Tutor-finance boundary

Tutor-specific details must come from tutor-owned, verified Django ledger
records. Never expose arbitrary Airflow logs, tokens, other tutors' payment
records, raw student identities or financial account details. Keep PayFast
notifications, booking commitments and bank transfers outside Airflow.
New payment analytics DAGs require separate idempotency/privacy tests.

## Verification before merge

~~~sh
python -m compileall -q backend/amaris_cms/airflow_client.py backend/amaris_cms/monitoring_admin.py airflow/dags
cd backend && python manage.py test tests.test_airflow_admin tests.test_monitoring_admin
~~~

Docker Compose startup and live API connectivity cannot be confirmed until
a VPS and protected API connection are provided. A merged PR alone is not
a completed deployment.
