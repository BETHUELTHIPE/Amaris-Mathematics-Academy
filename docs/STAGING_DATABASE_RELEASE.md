# Staging database gate and production promotion

## Render staging configuration (required)

Configure the existing Render staging service on the **staging** Git branch;
do not create another paid database or service.

- Use an **isolated staging PostgreSQL database** with a server-side
  `DATABASE_URL` connection string and an appropriate TLS requirement.
  Do not connect a test runner to the production student database.
- Set the Render **Pre-Deploy Command** to
  `python manage.py safe_migrate`. The command refuses non-PostgreSQL
  backends, destructive/data/custom-SQL or unknown migration operations,
  and checks that no unapplied migrations remain. Restore/initial database
  provisioning and non-additive migrations need a separately reviewed,
  backed-up procedure.
- Set `DJANGO_DEBUG=false`, a strong `DJANGO_SECRET_KEY`,
  `DJANGO_ALLOWED_HOSTS` for the staging Render host, and
  `CELERY_BROKER_URL` for staging Redis. Enable
  `ACCEPTANCE_GITHUB_OIDC_ENABLED=true` only on staging, using the
  existing GitHub Actions OIDC audience/repository restrictions.
- Do not configure live PayFast credentials or paid AI service tokens for
  the synthetic staging journey. Use sandbox adapters.

## Mandatory GitHub Actions order

The quality workflow runs backend migrations in CI, then verifies that no
migrations remain. Once build/security/frontend gates pass, the exact Git
SHA is pushed to the staging branch and the workflow waits until
`/health/version/` reports **that exact SHA** and readiness is HTTP 200.

Before any synthetic student checkout or course/lesson test, an authenticated
GitHub Actions OIDC request to
`/api/v1/student/acceptance/schema/` must report:

- `status: ready`
- `database: postgresql`
- `pending_migrations: 0`

This read-only endpoint fails closed for invalid identity, missing database,
unapplied migrations, or a SQLite fallback. The same gate requires both
PostgreSQL and Redis to be healthy in `/health/dependencies/`.

Next, the full synthetic course/search/PayFast-sandbox payment/status/
progress/resume/lesson journey must pass, followed by the staging
performance gate and evidence upload.

## Production release rules

Production promotion requires a fresh successful workflow on `main`, a
passing staging job, `deploy_production: true`, and the
`production_approval: APPROVE_PRODUCTION` manual input. The production
GitHub environment must require the authorized reviewer approval.

The production Render Blueprint uses the same `safe_migrate` pre-deploy
command and only the exact Docker image tagged with the full source Git SHA
may be promoted. Any migration involving removal, alteration, custom SQL,
data transformation or reversal is intentionally blocked from automatic
execution pending a separately approved backup, staging rehearsal and
recovery plan.

## Troubleshooting

If staging returns 503 or never reaches the expected SHA, inspect the
Render staging deploy and pre-deploy logs **without printing** database
credentials. Confirm the existing service's database host/pooler, TLS mode,
schema and migration history, and Redis connection. The GitHub workflow
does not change `DATABASE_URL` or execute direct SQL against production
to force the gate to pass.

Never bypass the schema/identity/health gate to approve production.
