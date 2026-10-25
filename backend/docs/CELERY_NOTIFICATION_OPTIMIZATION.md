# Celery notification throughput and reliability

The application uses **one Redis broker** with these worker queues:

| Queue | Worker | Tasks |
| --- | --- | --- |
| `critical` | `celery_worker` | Verified payment reconciliation, expired class holds |
| `default` | `celery_worker` | Scheduled CMS publishing |
| `notifications` | `celery_notifications` | Paid-course emails, class confirmations, class reminders |

Both Beat-submitted and directly submitted (`.delay()`/`.apply_async()`) tasks route to the same worker queues. The Compose worker health checks target each worker's own hostname rather than accepting an unrelated worker's response.

## Bounded notification backlog draining

Each periodic notification task selects up to `CELERY_NOTIFICATION_BATCH_SIZE` eligible records (default **10**, hard cap **25**, minimum **1**) **sequentially**. Each email has a separate short database transaction and a row lock, with `skip_locked` allowing multiple notification workers to avoid processing the same record concurrently.

A failed email propagates to the existing Celery retry policy; completed earlier messages in the batch remain committed. The task stops early when there are no eligible messages. The original single-email result (`0` or `1`) remains unchanged when at most one record is pending, preserving existing callers/tests. No new third-party service, charge, or external API is introduced.

The batch is a **bound**, not a guarantee of messages per minute. Actual throughput depends on SMTP latency, database health, worker memory and configured concurrency. Don't raise concurrency or batch size without staging tests and PostgreSQL connection headroom. A task may process up to 25 SMTP sends, so the existing Celery task time limit and email timeout must remain compatible.

## Verification

Run from `backend/`:

```bash
python manage.py test content.test_celery_optimization
python manage.py test content.test_payments content.test_live_classes
python manage.py test
```

CI runs the focused routing/batch suite and the full Django regression suite. These tests use local mocks for batching and the configured test email backend for actual ORM/email paths. No real PayFast, SMTP or Zoom requests are required.

Observe the actual `critical`, `default` and `notifications` queue depths and task failures through Redis/Flower and existing Prometheus infrastructure. Verify that Celery Beat has **one active scheduler** and that the notification worker consumes the `notifications` queue. If outgoing mail is not available, keep messages queued and address the SMTP failure; do not mark messages sent without provider acceptance.

## Failure model and rollout

Celery is at-least-once, not exactly-once. The existing send-then-mark transaction can duplicate a message if the worker crashes after SMTP acceptance but before the database transaction commits. This change preserves that behavior; **provider-level idempotency or a durable send receipt is still required to eliminate the crash window**.

Deploy to staging first, then inspect registration/contact and paid-course/Zoom flows, queued-email delivery, Beat scheduling, Flower visibility, recovery from a Redis interruption, and SIGTERM shutdown. No live sends are part of CI.

Rollback by restoring the previous immutable Git-SHA image with the protected release workflow. `CELERY_NOTIFICATION_BATCH_SIZE=1` is an additional conservative operational setting that restores one email per periodic execution while investigating a throughput regression; it is not a substitute for rollback or release approval.
