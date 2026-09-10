# Reliability and disaster recovery runbook

## Service objectives

| Control | Production target |
|---|---|
| Recovery Point Objective (RPO) | No more than 6 hours of PostgreSQL or locally stored media changes lost |
| Recovery Time Objective (RTO) | Restore essential registration, login, course access and payment records within 4 hours |
| Backup frequency | Every 6 hours, beginning when the backup service starts |
| Backup retention | 7 daily, 5 weekly and 12 monthly recovery points |
| Restore-testing frequency | Weekly, into a dedicated disposable PostgreSQL container |

These objectives begin only after the production backup repository, credentials and alert delivery are configured and the first successful restore test is recorded. Payment reconciliation with PayFast may be required after a database restore to recover gateway events received after the restored recovery point.

## Architecture and isolation

The `backup` service produces a PostgreSQL custom-format dump, validates its archive, packages the Django media volume, and sends both through Restic. Restic encrypts the repository before off-server storage. The encryption password must be kept in a production secret manager and separately escrowed for disaster recovery; losing it makes the backups unusable.

The `restore_tester` restores the latest automated snapshot into `restore_test_db`, which uses temporary storage and has no route to the production `db` service. A host-name guard refuses a restore test if its target equals the production database host.

Use a dedicated backup bucket in a different account or failure domain from production. Enable bucket versioning, retention protection or Object Lock, server-side KMS encryption, least-privilege credentials and cross-region replication. Never use the live media bucket as the only backup destination. When production media is stored directly in S3 instead of the Docker media volume, configure S3 replication into `MEDIA_BACKUP_BUCKET`; keep this separate from the Restic database repository.

No student-facing service depends on Prometheus, Grafana, Flower, cAdvisor, any exporter, pgAdmin, backup, or restore testing. A monitoring failure removes visibility but does not block registration, learning, checkout, enrolment, or payment notifications.

## Initial production activation

1. Create the off-server backup bucket and a least-privilege backup identity.
2. Store `RESTIC_PASSWORD`, object-storage credentials and KMS identifiers in the deployment secret manager. Keep an independently protected copy of the Restic password.
3. Set `RESTIC_REPOSITORY`, retention values and restore-test credentials. Set `MIGRATION_BACKUP_REQUIRED=true` in production.
4. Start the stack and confirm `backup`, `restore_test_db` and `restore_tester` are healthy.
5. Confirm Prometheus reports `amaris_backup_last_status 1` and `amaris_restore_test_last_status 1`.
6. Configure an Alertmanager or hosted-alert receiver for the supplied Prometheus rules. Do not consider alerting operational until a test alert reaches the on-call contact.

## Backup and validation commands

Run an immediate encrypted backup:

```bash
docker compose exec backup /app/ops/backup.sh
```

Run an isolated restore test immediately:

```bash
docker compose exec restore_tester /app/ops/restore-test.sh
```

List encrypted recovery points without printing credentials:

```bash
docker compose exec backup restic snapshots --tag amaris
```

Successful jobs update timestamped Prometheus text-file metrics. A dump archive check and sampled Restic repository check run on each backup. The weekly test performs a real database restore and verifies core Django, payment and enrolment tables.

## PostgreSQL recovery procedure

1. Declare the incident, record its correlation/ticket reference, and stop or redirect writes. Keep the original database volume intact for investigation.
2. Identify the newest known-good snapshot at or before the incident. Record its snapshot ID and timestamp.
3. Provision a new isolated PostgreSQL instance. Never restore over the damaged production cluster.
4. Restore the selected Restic snapshot to a temporary directory, run `pg_restore --list`, then restore with `--exit-on-error --no-owner --no-privileges` into the new database.
5. Run Django system checks, migration consistency checks, record counts, payment/enrolment invariants and a read-only application smoke test.
6. Reconcile verified PayFast transactions received after the restored recovery point. Do not mark payments paid from browser redirects, screenshots or frontend state.
7. Switch `DATABASE_URL` to the recovered cluster, start one web instance, verify readiness, then restore normal capacity.
8. Monitor errors, reconciliation results and gateway notifications. Preserve the failed cluster and recovery logs according to the incident policy.

## Media recovery procedure

For Docker-volume media, restore `media.tar` from the same Restic snapshot into a new empty media volume, scan uploads, validate permissions, and then mount the recovered volume. For primary S3 media, recover from the replicated/versioned backup bucket into a new bucket, validate object counts and representative files, and change the storage configuration only after access-control checks pass.

Paid resources must remain private throughout recovery. Never recover private files into an NGINX public-static path.

## Redis and Celery failure procedure

Redis is not part of Django readiness and `web` does not depend on Redis startup. During a Redis incident, public pages, authenticated requests and direct database operations continue; Celery, Beat and Flower are degraded.

Redis uses AOF with `appendfsync everysec`, periodic snapshots and a no-eviction policy. If Redis data is corrupt, preserve the old volume, start a clean Redis instance, then restart Celery Worker and Beat. Celery tasks acknowledge late, reject work lost with a worker, retry database connection failures with exponential backoff and jitter, and limit prefetching. All important tasks must remain idempotent because recovery may redeliver work.

Payment reconciliation also runs in a separate database-only watchdog, so Redis failure cannot prevent it from repairing enrolment linkage for payments already verified by the server-side gateway path.

## Payment reconciliation

The reconciliation service never changes a payment to `paid`. It only considers an existing paid record whose `gateway_verified_at` value proves that the server-side gateway verification path succeeded. It creates or activates the unique student/course enrolment idempotently and links the payment. Cancelled enrolments are reported unresolved and require authorised review.

Run it manually after recovery:

```bash
docker compose exec web python manage.py reconcile_payments
```

Review immutable reconciliation summaries in Jazzmin Admin. Investigate unverified paid records and cancelled access; never resolve them with direct database edits.

## Graceful shutdown

Use `docker compose stop` and allow the configured grace periods to expire. NGINX receives `SIGQUIT`, Gunicorn and Celery receive `SIGTERM`, PostgreSQL receives 60 seconds, and backup/restore jobs receive up to 30 minutes. Do not use `docker compose kill` during ordinary deployments. Drain load-balancer traffic before stopping web containers.

## Database migration and rollback plan

Production migrations run through the one-shot `migrate` service. With `MIGRATION_BACKUP_REQUIRED=true`, a verified encrypted `pre-migration` backup must succeed before Django applies changes.

Use expand/migrate/contract changes: add backwards-compatible structures first, deploy compatible code, migrate data in controlled batches, and remove old structures only in a later release. Every migration must document reversibility, runtime and lock risk in the release record.

If a deployment fails, first roll the application image back while keeping a backwards-compatible schema. Reverse a Django migration only when its reverse operation was tested against a restored production-like copy and is known to be non-destructive. Otherwise restore the pre-migration snapshot into a new database, validate it, switch application traffic, and retain the failed database for analysis. Never improvise destructive SQL during an incident.

## Health, uptime and alert response

- `/health/live/` proves only that Django is running.
- `/health/ready/` checks PostgreSQL because it is required for student requests.
- `/health/dependencies/` reports PostgreSQL and Redis without hostnames, credentials or exception details. Redis failure returns `degraded` with HTTP 200; PostgreSQL failure returns HTTP 503.
- Blackbox Exporter probes the public Sites URL and internal NGINX readiness route.
- PostgreSQL, Redis, host, container and recovery metrics are scraped by Prometheus and visualised in Grafana.

Critical alerts cover public-site outage, backend readiness, PostgreSQL failure, stale or failed backups and low disk space. Warning alerts cover Redis degradation, failed/stale restore tests and monitoring component failures. Monitoring alerts must route separately from application control paths; an unavailable receiver must never change application health.

## Recovery exercise record

Run a documented disaster-recovery exercise at least quarterly in addition to the weekly automated restore. Record snapshot age, restoration start/end times, achieved RPO/RTO, validation results, payment reconciliation result, missing data, operator names, incident reference and corrective actions. Rotate backup credentials after suspected exposure and test again after rotation.
