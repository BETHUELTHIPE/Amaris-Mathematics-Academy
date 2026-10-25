# Proving Celery runs in the real staging environment

The passing Python/Django GitHub Actions suite verifies task configuration and
application code. It does **not** prove that the live staging Redis broker,
Celery workers, Beat scheduler or SMTP services are operating.

## Preflight: staging must be healthy

The current staging acceptance run reported `/health/live/` = 200 and
`/health/ready/` = 503. Readiness in
`amaris_cms/urls.py` requires a real PostgreSQL `SELECT 1`.
Fix that environment-specific PostgreSQL connection before treating any
staging queue result as release evidence. The staging workflow now reports
only `postgresql` / `redis` health booleans, without leaking connection
strings. Check staging Render environment/database attachments and private
application logs. Never paste `DATABASE_URL`, passwords or tokens in CI logs.

## Actual worker execution (no student data, emails or charges)

After the **candidate Git SHA** is deployed to the staging web process and
both worker types, execute from a secure **staging backend shell/job** with
the same `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` as staging
workers:

```bash
python manage.py verify_celery_runtime --timeout 20
```

This command publishes one side-effect-free nonce probe per queue and **waits
for the matching result** through Redis:

- `critical`: processed by the core payment/hold-expiry worker
- `default`: processed by the core CMS worker
- `notifications`: processed by the dedicated notification worker

Every queue must report PASS. A missing worker, wrong routing key, broken
broker, absent result backend or eager/local execution mode fails the command.
It performs no PayFast, SMS, WhatsApp, OpenAI, Zoom, YouTube or SMTP request.
Do **not** run it against a previously deployed image lacking the new task.
Never claim a queued probe is delivered unless the result was received.

## Additional operational evidence before production

Confirm through private Render logs, Flower and Redis monitoring that the
actual staging release SHA is running; exactly one Beat scheduler is active;
both worker types remain healthy; notification tasks are **consumed** from
`notifications`; scheduled ticks are emitted; and the payment watchdog and
Beat do not double-schedule reconciliation. Verify restart/recovery and
backlog drain. A successful nonce probe proves message execution, **not**
provider email delivery, exactly-once notifications or correct payment
outcomes. End-to-end outbox and email staging tests still require separate
controlled evidence; do not trigger real charges or mass emails.

The staging acceptance check also requires readiness, security-safe branded
errors and dependency reporting. **No production promotion** until its
required CI checks, a genuine staging deployment/test, backup/restore and
approval gates pass.

To diagnose a 503 without posting secrets, verify: staging Render service is
using the intended PostgreSQL instance; `DATABASE_URL` is configured as a
secret; provider-required TLS is enabled; host/port/credentials are valid;
and the database allows connections from the service. Inspect sanitized
Render errors privately to distinguish DNS/TLS/authentication/pool exhaustion.

## Safe automated coverage

CI runs `python manage.py test content.test_celery_runtime` with mocks,
including queue coverage, eager-mode refusal, wrong queue responses,
broker failures and invalid timeout. These tests **cannot replace** executing
the command inside staging against its real broker and workers.
