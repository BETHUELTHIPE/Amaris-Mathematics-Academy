# Share the existing website container with Airflow

This is an **optional image variant**, not a new Render service. Django,
Airflow API, scheduler and DAG processor run as separate processes inside one
container and share its existing CPU/RAM. Docker-in-Docker, another VPS, paid
Airflow services, new disks and new database instances are not required by it.
Airflow and Django use different Python dependency environments.

## What this changes

- Existing default Docker builds remain Django-only.
- Build the combined variant with:
  `docker build --target shared-airflow -t amaris-shared-airflow backend`.
- On Render, use the existing backend service, `backend/Dockerfile`, Docker
  context `backend`, and non-secret build argument
  `AMARIS_IMAGE_VARIANT=shared-airflow`. Render translates declared env vars
  to Docker build args. Clear the old native Python start command so the image
  CMD starts the process supervisor. Do not import `airflow/render/render.yaml`;
  that alternative creates separate paid services.
- The Airflow API binds **only to 127.0.0.1:8443**, with a container-local
  certificate explicitly trusted by Django and the task SDK. It is not an
  additional public service or a frontend iframe. Only Django binds `$PORT`.
- Only the bundled website health DAG is included and it starts paused.
- Website secrets (PayFast, Supabase service key, AI key, etc.) are not passed
  to Airflow child processes. Processes still share a container/user; this is
  not the isolation provided by separate services.

## Existing persistent database required

Airflow needs persistent metadata independently of its container filesystem.
Use a private schema and dedicated restricted role on a suitable **existing**
PostgreSQL instance, after reviewing connection/storage capacity. This profile
does not provision a database or automatically create/alter production roles.
Never use SQLite or an ephemeral PostgreSQL process in the web container.

Set these managed runtime secrets:

| Variable | Meaning |
| --- | --- |
| SHARED_AIRFLOW_ENABLED | `true` only after capacity and staging checks |
| SHARED_AIRFLOW_DATABASE_URL | Existing PostgreSQL endpoint with dedicated metadata credentials, session/direct connection, TLS required off-host |
| SHARED_AIRFLOW_SCHEMA | Existing private schema owned by that role, e.g. `amaris_airflow` |
| SHARED_AIRFLOW_FERNET_KEY | Valid Airflow Fernet key, retained with metadata backups |
| SHARED_AIRFLOW_JWT_SECRET | Random runtime signing secret |
| SHARED_AIRFLOW_API_SECRET | Random runtime API secret |
| AIRFLOW_API_TOKEN | Short-lived Viewer-only service token, with renewal before expiry |
| AIRFLOW_MONITORING_ENABLED | `true` only after the read-only admin API passes |

The role must not be superuser, bypass RLS, create roles/databases, or access
application tables outside its schema. Preflight checks enforce these
boundaries. Keep the schema outside Supabase's exposed API schemas; no grants
to anon/authenticated. The backend database role is rejected for Airflow.
Check FAB tables, not only Airflow core tables, stay in the private schema.
No live Supabase changes have been made by this implementation.

After backup/restore and role-isolation review, migrate the Airflow schema
explicitly using `python ops/shared_airflow/run.py migrate` in the combined
image. Normal web startup only checks migrations. Create FAB operator/Viewer
identities through `python ops/shared_airflow/run.py cli users create` (omit
password arguments and use the CLI's secure prompt), and verify anonymous
denial and rejected Viewer writes. The `cli` adapter validates metadata
isolation and supplies the same isolated environment as the running services.
The launcher supplies `AIRFLOW_API_BASE_URL` and the local CA path to Django.
Only superusers may view `/admin/airflow/`.

## Capacity and release gate

The current live backend is a **native Python** Render service, with a 2 GB
allocation. It does not currently run this Docker image. Render supports
changing the runtime of an existing non-static service; confirm the reviewed
source and keep the existing plan, URL and environment. Do not create a
replacement paid service or upgrade the plan without approval.

Airflow recommends at least 4 GB for its own typical deployment. Sharing a
2 GB container is therefore an experiment requiring actual measurement,
not a supported capacity claim. The CI image test caps this container at
2 GB with one Django worker, uses disposable databases, records peak memory and verifies website
availability while running a synthetic DAG. It must pass before considering
staging, followed by representative website load and real metadata isolation
checks. Passing a small smoke test does not establish production capacity.

The supervisor gracefully stops process groups on SIGTERM. An Airflow
preflight failure leaves Django running with the monitor unavailable; a
runtime Airflow process exit is logged while Django stays up. The whole
container remains a shared failure domain: an OOM kill can affect the website.
Local Airflow logs are ephemeral. Certificate trust is container-local and
the certificate lasts 30 days; deployments/restarts rotate it. Restart or
renew before expiry. Remote retention and automated token renewal must be
configured before treating this as production orchestration.

To roll back, first disable SHARED_AIRFLOW_ENABLED, restore the previous
verified image/native runtime and retain the private metadata schema. Do not
delete student tables, change existing services' billing plans, or drop the
metadata schema as part of an application rollback.
