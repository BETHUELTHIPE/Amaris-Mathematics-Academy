# Celery Beat runtime and optimization

The application has a **single Celery Beat service** and separate workers for
`critical,default` tasks and `notifications` tasks. Do not scale Beat to
multiple replicas against the same Redis broker: Beat publishes duplicate jobs
when multiple schedulers run. Worker replicas may scale independently.

## Scheduling

`amaris_cms.beat_schedule.build_beat_schedule` preserves the existing production
cadences: content publish (60s), payment reconciliation (300s), transactional
email/booking confirmation (30s), live-class reminder (60s), and expired booking
hold cleanup (300s). Booking reminders still use the existing 30-minute
eligibility window. All tasks use explicitly named queues and polling messages
expire shortly before their next Beat tick, so an overloaded broker does not
accumulate stale duplicate polls. The durable work remains in PostgreSQL; the
next tick can retry. Keep worker capacity sufficient for time-sensitive reminders.

In the default Docker Compose topology the separate `payment_reconciler`
watchdog already runs every 900 seconds. Therefore **only the Beat container**
sets `CELERY_BEAT_RECONCILIATION_ENABLED=false`, removing its otherwise
duplicate 300-second reconciliation tick. In standalone deployments (including
Render with only Beat, Redis and workers), the default remains `true`. Never
disable both scheduling mechanisms. If you remove the watchdog from Compose,
remove the Beat override to restore reconciliation.

Task routing is defined in `amaris_cms/celery.py`. Notification tasks are routed
to `notifications` for both periodic dispatch and calls to `.delay()`, and
payment reconciliation uses `critical`. This avoids mixing student email
delivery with general content jobs.

## Verification

Run `python manage.py test content.test_beat_schedule` from `backend/`, plus the
existing payment, booking and notification suites. Verify a real staging
instance with Redis, Beat and both worker types before production promotion.
Watch broker queue depths and age, missed reminder windows, task errors,
reconciliation runs, Beat process restarts, CPU and memory. The Compose Beat
health check confirms the process exists, not that email or scheduling delivered
an external effect. Do not count that process check as an end-to-end pass.

Rollback: redeploy the previous immutable image Git SHA and restore the previous
Beat configuration. No database schema migration is required by this change.
This optimization does **not** prove a number of concurrent users, reliable SMTP
delivery or production scheduling until exercised against staging/production.
