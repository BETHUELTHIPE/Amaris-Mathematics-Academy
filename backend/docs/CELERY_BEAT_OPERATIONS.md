# Celery Beat operations (Amaris)

## Production schedule ownership

Run **exactly one Celery Beat instance per environment**. The scheduler
publishes due website content every 60 seconds. Payment reconciliation is
scheduled every 300 seconds **only when** `CELERY_BEAT_PAYMENT_RECONCILIATION_ENABLED=true`.

The Docker Compose deployment includes a dedicated `payment_reconciler`
process, so Compose explicitly sets
`CELERY_BEAT_PAYMENT_RECONCILIATION_ENABLED=false` on `celery_beat`.
The standalone reconciler runs every 300 seconds by default. Existing
environment overrides of `PAYMENT_RECONCILIATION_INTERVAL_SECONDS`
continue to take precedence. This avoids two recurring triggers for the
same database reconciliation task.

For a Render deployment that runs Beat but **does not** run a standalone
payment reconciler, set
`CELERY_BEAT_PAYMENT_RECONCILIATION_ENABLED=true` on the Beat service.
Never use both schedulers for the payment task at the same time.

## Durable, safe scheduling

Compose persists Beat's local scheduler database at
`/app/beat/celerybeat-schedule` in the named `celery_beat_state` volume.
The image owns that directory as the non-root `amaris` user. Do not
remove that volume during routine upgrades or restarts.

The scheduler synchronizes its state after every dispatched task and
uses at most a 30-second loop interval. Publishing tasks older than 60
seconds and reconciliation tasks older than 300 seconds expire from a
worker backlog; later ticks recheck the current database state. Both
business operations must remain idempotent, particularly under retries.

## Staging checks before production

1. Run `docker compose --env-file backend/.env -f backend/docker-compose.yml config --quiet` with a correctly configured **staging** environment file.
2. Start PostgreSQL, Redis, the migrations, Celery worker, Beat and the
   dedicated payment reconciler in staging. Keep exactly one Beat process.
3. Confirm `celery_beat` stays healthy, the
   `celery_beat_state` volume exists and is writable, and Beat logs show
   periodic content dispatch.
4. Verify a due staging content record publishes once; verify the
   reconciler processes only provider-verified paid records. Use synthetic
   sandbox data and do not initiate real payments.
5. Restart Beat and check that the schedule volume survives, worker
   processing resumes, and no duplicate payment periodic jobs are sent.
6. Monitor queue depth, worker failures, task runtime, Redis memory,
   PostgreSQL latency, and Flower/Prometheus metrics. A healthy Beat
   process alone does **not** prove tasks are executing successfully.

Do not deploy this change to production until the GitHub Actions,
staging checks and release approval gates pass.
