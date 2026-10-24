# Amaris Supabase → private Render Grafana

## Data security
- Aggregate-only views in the `amaris_reporting` schema. **No raw student, email, phone, payment, bank, or provider payload fields** are exposed.
- A separate `amaris_grafana_ro` PostgreSQL role has `SELECT` on these views only; it does not have raw table `SELECT`.
- The role is created as **NOLOGIN** by `sql/amaris_reporting.sql`. Activate with a strong separate password only when configuring the corresponding Grafana environment.
- The default transaction mode is read-only, query timeout is 5 seconds and connection limit is 3.
- Treat these views as a privileged reporting surface. They intentionally aggregate base tables through owned views despite restrictive RLS; **do not expose the reporting schema in Supabase Data API**.
- Grafana remains a **Render private service**, with the Django Admin monitoring gateway restricted to superusers. Never expose Grafana directly or give students Explore access.
- Keep staging and production connections separate: a separate pooler host, username and password per database.

## Database migration
Apply `sql/amaris_reporting.sql` first to staging and verify aggregate read rights and raw-data denial. When production is approved, verify a backup and apply the same schema-only migration there. No Django migrations and no destructive table changes.

## Grafana configuration
The Docker startup script only activates a PostgreSQL datasource if all three respective environment variables exist. The connection must be copied from **Supabase → Connect → Session pooler**, which supports Render's IPv4 egress; do not guess the pooler host.

Staging:
- `AMARIS_GRAFANA_STAGING_DB_HOSTPORT`: approved staging session-pooler `host:5432`
- `AMARIS_GRAFANA_STAGING_DB_USER`: `amaris_grafana_ro.atyhhjwwxgzeurnwayay`
- `AMARIS_GRAFANA_STAGING_DB_PASSWORD`: separate strong credential (Render secret)

Production:
- `AMARIS_GRAFANA_PRODUCTION_DB_HOSTPORT`: **exact** production Supabase session-pooler `host:5432`
- `AMARIS_GRAFANA_PRODUCTION_DB_USER`: `amaris_grafana_ro.epkcuseloinygkakxxdu`
- `AMARIS_GRAFANA_PRODUCTION_DB_PASSWORD`: separately rotated Render secret

TLS required, up to 2 open connections per datasource, non-editable provisioning and 1-minute panel refresh. Prometheus remains the default source, unchanged.

## Dashboard scope
- Verified revenue / transaction counts from PayFast-verified **live classes, courses and video requests**; ZAR only.
- Booking confirmation, pending payment, manual review.
- Course/live/video invoices issued (invoice presence is not necessarily proof of archive or inbox delivery).
- Student signups, email dispatch markers (not recipient mailbox delivery), video-request activity.

No student-level detail. A verified payment and a dispatched email are **not** proof of inbox delivery.

## Release gates
1. Validate aggregate views and read-only role on staging.
2. Provision secrets in Render (never commit credentials).
3. Review & merge the code, then trigger the existing private Grafana service's **manual** deployment (its auto-deploy is off).
4. Confirm Render build is live, datasource Save & Test succeeds and each panel returns real counts.
5. Confirm Django Admin proxy supports Grafana's JSON datasource queries; the existing gateway currently forwards GET only. Keep it superuser-only.
6. After production backup and approval, apply the production reporting schema/role, configure its **separate** pooled connection and check same-origin authenticated dashboards.
