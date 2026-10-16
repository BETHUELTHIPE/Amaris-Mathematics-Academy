# Dockerised Airflow on Render

This **opt-in paid** Blueprint adapts `../compose.yml` for Render. No VPS, SSH
hostname or purchased domain is needed. Render runs each Docker process as a
separate service. This file does not modify the existing root Blueprint,
production Django service, student frontend, Supabase, PayFast or Celery.

## Resources proposed for review

| Resource | Render type | Proposed plan | Purpose |
| --- | --- | --- | --- |
| amaris-airflow-api | Private Docker service | standard | FAB-authenticated API, TLS on 8443 |
| amaris-airflow-scheduler | Docker worker | standard | LocalExecutor, maximum 2 simultaneous tasks |
| amaris-airflow-dag-processor | Docker worker | starter | Parse the same baked-in DAGs |
| amaris-airflow-metadata | Managed PostgreSQL 17 | basic-1gb | Dedicated Airflow + FAB metadata |
| airflow-task-logs | Scheduler disk | 1 GB | Persist local execution logs |

All resources use Frankfurt, the existing Django backend's region. Proposed
plans are starting points, not capacity evidence. Obtain the current monthly
quote from Render, including disk and database storage, **before importing**.
`autoDeployTrigger: off` prevents subsequent automatic releases, but does NOT
prevent initial provisioning/billing when a Blueprint is created.

## Differences from Compose

- DAGs are copied into a versioned Docker image instead of host bind mounts.
- Managed metadata PostgreSQL replaces the Compose PostgreSQL container.
- `fromDatabase` and `fromService` supply private addresses and credentials;
  start.py constructs URLs because Blueprints do not interpolate strings.
- API alone runs `db migrate` as its pre-deploy command. With FAB selected,
  Airflow loads its FAB database manager and migrates auth tables as well.
- Workers wait for schema migrations and verified TLS API reachability.
- Shared JWT/API secrets are generated once in an environment group. The
  Fernet key is entered once on the API and referenced by workers.
- The server private TLS key is available only to the API; workers receive
  the issuing CA. TLS verification and hostname checks stay enabled.
- FAB replaces the Compose evaluation-only Simple Auth Manager. No default
  administrator, public login bypass or automatic user creation is installed.
- The health DAG is initially paused; unpause it only after acceptance checks.
- StatsD is OFF in this baseline. A private exporter/scrape path must be
  separately configured and tested before enabling metrics. Existing Grafana
  dashboards must show no data until real metrics arrive.

## Release and first boot

1. Review this PR and dependency PR #219; merge only after checks. The Blueprint
   uses `branch: main`, so all referenced paths must exist on main before import.
   Deploy API and both workers from the same reviewed Git SHA. Auto-deploy is
   deliberately off to prevent mixed image/DAG releases.
2. Review and approve the additional recurring cost. Create a **new, separate**
   Render Blueprint using `airflow/render/render.yaml` in this repository.
   Do not replace the existing application Blueprint or re-import its services.
3. Configure a valid new Fernet key in `AIRFLOW__CORE__FERNET_KEY` on the API;
   never reuse Django/Supabase keys. Store it with your backup recovery secrets.
4. After Render allocates the API's internal hostname, obtain an internal-CA
   issued server certificate whose DNS SAN contains that **exact hostname**.
   No public domain or public certificate is required. Use an operated private
   CA with renewal/expiry alerts; an unverified certificate is not acceptable.
   The API may remain unready until certificate provisioning finishes.
5. Set API runtime secrets `AIRFLOW_TLS_CA_PEM` (issuing CA certificate chain),
   `AIRFLOW_TLS_CERT_PEM` (server certificate/full chain), and
   `AIRFLOW_TLS_KEY_PEM` (matching private key). Preserve actual PEM newlines.
   No certificate/key belongs in Git, images or frontend environment variables.
   Startup materialises these as mode-0600 files; do not use Docker build ARGs.
6. Deploy API first and confirm its metadata migration succeeds. Deploy both
   workers at the same SHA. There is no Compose `depends_on` ordering in Render;
   worker waits are bounded and fail closed if dependencies never become ready.
7. Through the API service's authenticated Render shell, create a separate
   operator account and a **Viewer-only** service identity using FAB. Use a
   DAG-specific custom read role if additional sensitive DAGs are later added.
   Generate a short-lived bearer token for the service identity via FAB's
   authenticated `/auth/token` endpoint. Do not use an administrator token.
   Configure a tested renewal/rotation procedure before enabling Django.
8. Verify an anonymous request cannot list DAGs and the Viewer cannot trigger,
   edit, delete or clear a DAG/run/task. Validate API health, scheduler and DAG
   processor heartbeats, DAG import errors, and a real completed health DAG run.
   Use `airflow dags unpause amaris_service_health` only for this read-only DAG.
9. Back up metadata PostgreSQL and verify an isolated restore, including Fernet
   recovery. Set retention and certificate/token-expiry alerts. This is a new
   metadata database; it must never use the Amaris student production database.

## Attach to Django Admin (staging first)

The production admin monitor still depends on PR #222 and the CA-client change
in this PR being promoted through the normal backend release flow. This
Blueprint intentionally does not mutate your existing backend configuration.

Upload the issuing CA chain as a Render **secret file** named `airflow-ca.pem`
on the Django service. Set server-side variables:

| Variable | Value |
| --- | --- |
| AIRFLOW_API_BASE_URL | `https://ACTUAL_INTERNAL_HOSTNAME:8443` |
| AIRFLOW_API_CA_CERT_FILE | `/etc/secrets/airflow-ca.pem` |
| AIRFLOW_API_TOKEN | Viewer-only bearer token, rotated before expiry |
| AIRFLOW_MONITORED_DAGS | `amaris_service_health` |
| AIRFLOW_MONITORING_ENABLED | `true` only after authenticated connectivity passes |

Render's private API has no public `onrender.com` URL. Confirm workspace,
region and environment isolation permit Django to reach the API. Staging and
production must not share write access or auth tokens indiscriminately.

Verify `/admin/airflow/` as a superuser and confirm staff, tutor and student
accounts are denied. Confirm real run/task states update, and an expired token
or unavailable API produces an unavailable state without fabricated success.
Student/tutor dashboards continue to use owner-scoped Django records; this
change does not expose raw Airflow APIs or task logs to either role.

## Operational limits and rollback

- This baseline contains only `amaris_service_health`; it does not orchestrate
  payments, tutor transfers, invoices or every Django transaction.
- Local task logs persist on the scheduler disk, but cross-service UI log
  retrieval and off-site log retention are not configured. The admin monitor
  consumes run/task states, never task logs. Add supported remote logging
  before relying on the Airflow UI for production troubleshooting.
- Private TLS services need an external periodic authenticated probe of API
  health and job heartbeats. A Render deploy status/TCP listener alone does
  not prove scheduler health. No such live probe has been activated here.
- For UI/API problems, disable `AIRFLOW_MONITORING_ENABLED` on Django first;
  the normal application stays independent. Pause the DAG and stop workers
  before an Airflow rollback. Retain the metadata database and restore only
  through a verified backup procedure; do not run destructive downgrades.
- This adaptation is not live deployment evidence. Image build, fresh-DB
  boot and live private connectivity must pass before production acceptance.

## Validation

The integration workflow checks the official Render JSON schema, TLS and
startup behavior, Docker build/fresh PostgreSQL boot, and Django authorization.
It uses generated, disposable credentials and certificates only.
