# Amaris live tutoring: paid booking notifications (production backend)

The frontend booking change is a separate PR based on the live-student release branch. **Deploy this backend before the frontend**, because the new tutor selector requires `tutor_id` from `GET /live-classes/slots/`.

## Preferred zero-additional-service-cost deployment: existing Render web instance

**Finding, verified in the connected account:** Production Django `amaris-production-web` already runs as **one paid Standard Render instance** (2 GB RAM limit), with recent usage of about 130–160 MB; the private `amaris-production-broker` already exists. No extra worker, scheduler, host, external Redis allowlist, or newly billed Render service is required if the existing instance can reliably support the load.

The backend now has an **opt-in Gunicorn-master supervisor** in `amaris_cms/colocated_notifications.py`. With `AMARIS_COLOCATE_NOTIFICATIONS=true` set **only on the existing production Django web service**, its `gunicorn.conf.py` starts exactly one Celery worker (`notifications` queue, prefork concurrency 1) and one Beat scheduler after the web listener is ready. Each child requires the existing `ops/check_notifications.py` preflight: correct database migration `0017`, broker access and Beat routing, plus authenticated SMTP for the worker. The scheduler starts **only after the notification worker passes its checks**. A short-lived **private Redis lease** elects one Beat leader during rolling web deployments to avoid duplicate schedulers. The supervisor restarts failed children after a backoff without shutting down the student website. Child processes are terminated on Gunicorn shutdown.

This implementation is **disabled by default**, and MUST NOT be enabled before the genuine production Supabase backup/restore and staging PayFast sandbox email acceptance. It shares CPU/RAM with Django; monitor Gunicorn latency, memory, email queue lag, and errors. Keep this web service at **exactly one instance** unless the singleton-leader and capacity controls have been independently load-tested. Its no-extra-charge operation is not a promise of limitless capacity, exactly-once SMTP delivery or zero infrastructure cost: it reuses the already-paid Standard web plan.

**Release procedure:**
1. Prove the production Supabase backup and isolated restore; test the additive migration `0017` safely on staging, and pass backend CI/payment regression checks.
2. Verify the existing web service's production `CELERY_BROKER_URL` points at the **private Render broker**, and securely set `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`, `EMAIL_PORT` and TLS options. Never disclose SMTP secrets.
3. Merge and deploy backend PR #336 to `production-release-20260923`, verify migration `0017` is applied and Django serves healthy requests. Leave the opt-in switch off during this step.
4. On **existing** Render web service `srv-dapn6b3tqb8s73d3r7n0`, set `AMARIS_COLOCATE_NOTIFICATIONS=true`. This changes only that service's runtime configuration; it does not provision or bill new services. Redeploy that same service once, inspect logs for `Amaris notifications started` and `Amaris beat started`, and verify queue/Beat lease health.
5. Perform one verified synthetic PayFast **sandbox** booking through staging, check student/tutor/admin email inboxes and matching student/admin PDF invoices, confirm 30-minute reminder and non-duplication. Only then deploy frontend PR #335.
6. If web latency, memory, worker restarts or duplicate emails increase, set `AMARIS_COLOCATE_NOTIFICATIONS=false` and redeploy the existing service. The Django student website should remain available when a sidecar fails; treat lost emails as a critical operations issue and remediate before advertising 24/7 notifications.

**Deployment status:** No switch was enabled, no production backup/restore was completed here, and the migration has not been applied. Both PRs remain draft and production still uses the previous booking code.

## API and recipients

- `GET /live-classes/slots/?tutor_id=<id>` optionally limits availability to a tutor with published free slots. The response includes `tutor_id`, not the private Zoom link.
- The existing server-side PayFast verification, R250 per hour, 1–24 whole-hour sessions, booking holds, ownership permissions and 30-minute reminders remain in place.
- Only after payment is provider-verified and the booking is **confirmed** does the notification worker email the student with PDF invoice and Zoom link, the selected tutor with full booking details, and Django administrators with full booking details and the same archived PDF invoice. The tutor receives no invoice attachment. The student's private invoice remains downloadable after lesson completion.
- Admin notifications use BCC to active superusers, the SiteSettings contact email and optional `BOOKING_ADMIN_NOTIFICATION_EMAILS` (comma-separated) from Render configuration.
- Details sent to the assigned tutor/admin: booking reference, verified payment status, student name/email/optional telephone, tutor, programme, subject, grade, topic, SAST start/end, duration, amount, invoice number and Zoom URL.
- Individual `confirmation_sent_at`, `tutor_confirmation_sent_at`, `admin_confirmation_sent_at` receipt fields are read-only in Django Admin. Backend acceptance does **not** prove inbox receipt; staging SMTP tests remain mandatory.
- The migration marks all pre-existing bookings `staff_notification_required=False` to prevent misleading retroactive booking alerts. New ORM-created bookings default to true.

## Deployment gate

1. Check production migration head `0016_separate_location_fields`, then test `0017_liveclass_recipient_notifications` against a staging clone.
2. Back up and perform an isolated restore of production Supabase data **before** any production migration. Record backup ID and restore evidence.
3. Configure outbound SMTP for the notification worker and optionally a monitored `BOOKING_ADMIN_NOTIFICATION_EMAILS`. Confirm Django superuser accounts and SiteSettings use controlled email addresses.
4. Run Django `manage.py check`, migration plan/check and `python manage.py test content.test_live_classes`; verify all existing tutor, finance, location and permission tests.
5. Use a synthetic tutor with an overnight 23:30 SAST published slot and a separate daytime tutor. Verify the optional tutor query, hourly server pricing, no Zoom data in public responses, and checkout double-booking rejection.
6. Perform one isolated real PayFast **sandbox** payment callback with synthetic student data; verify the student, tutor and admin inboxes each received the correct email, and that the student/admin received byte-identical PDF invoices while the tutor received booking details. Retry the worker and ensure no duplicate invoice. Never use live money for acceptance.
7. Confirm the notification worker and scheduler are running; test the 30-minute student reminder, staged shutdown and retry.
8. Deploy backend, verify runtime SHA, migrations, HTTP smoke checks and error logs; only then release the separately tested frontend PR. Keep the previous production backend SHA as rollback target, and stop if schema compatibility or SMTP is unresolved.

**Current state:** Code prepared in a draft PR only. No production database changes, actual payments or external confirmation emails were performed.

## Validation update — 24 October 2026 (SAST)

- Local Python 3.12: the full 240-test Django suite completed successfully with five skips after collecting static assets. This includes booking/payment, invoice ownership, staff BCC privacy, independent delivery markers, identical student/admin invoice attachments and completed-lesson invoice downloads. Production's Python 3.13/PostgreSQL CI remains a separate gate.
- All 11 colocated supervisor tests passed, including a regression that prevents Beat startup if its Redis lease expires during dependency preflight. Ruff, mypy (39 source files), formatting comparison and migration drift checks passed. Notifications-only Beat exposes seven schedules, all on the notifications queue.
- Read-only Supabase checks confirmed that staging and production are both at `content.0016_separate_location_fields`. Migration `0017` has not been applied to either live database.
- The preceding GitHub backup/restore job passed against disposable PostgreSQL databases with synthetic data. It does **not** prove that production has a retained encrypted backup or a verified restore.
- Render lists a monitoring-only worker consuming `monitoring-verification`; it does not list a booking notification worker or Beat service. Colocated activation, production SMTP configuration and actual inbox delivery are not verified.
- No new paid resources or external Redis access were added. Production deployment remains blocked by current release CI, the production backup/restore evidence and deployed staging sandbox email acceptance.

## No new paid Render services: optimized two-container Docker option

**Cost boundary:** Render does not have a Free plan for background workers or cron jobs. The paid `render-notifications.yaml` Blueprint was removed. **Do not create new paid Render services** for this release. Instead `backend/compose.notifications.yml` describes exactly two containers which can run on an **existing always-on host** (e.g., an owned computer/VM with Docker Engine and Compose). There is no evidence of an available always-on Docker host connected to this account. An owned host consumes electricity/network resources and does not inherit a Render uptime/SLA.

Only these processes run:

- `notification_worker` listens to the `notifications` Celery queue, with one prefork child, one prefetched message, a 512 MiB RAM cap, 0.50 CPU, recycling after 100 jobs or 220 MB child RSS, and a queue-specific healthcheck.
- `celery_beat` runs exactly once, with a 256 MiB RAM cap, 0.25 CPU, and `CELERY_NOTIFICATIONS_ONLY_BEAT=true` so this lightweight instance publishes **only** jobs scheduled for the `notifications` queue. Do not run a second Beat against the same Redis database. The critical/default queues need their *separate existing* consumers if those tasks are still required; this setup does **not** replace a payment reconciliation worker.

Both containers share one prebuilt Django image; they have no public ports, read-only root filesystems, writable ephemeral `/tmp` only, dropped Linux capabilities, a non-root image user, restart policies, and fail-closed connection checks.

### Production network and secrets

The existing Render `amaris-production-broker` uses an **internal-only** IP allowlist as currently configured. A separate host **cannot** use its internal URL. If a fixed public IPv4 exists for the Docker host, an authorized administrator can permit **only that /32 address** in Render Key Value networking and use its authenticated TLS external `rediss://` URL. **Never** allow `0.0.0.0/0`. This alters the broker's network exposure and must be security-reviewed before making a change. Alternatively use an already-authorized private-network broker reachable by both the production Django app and the Docker host. Do not point Django and Beat at different Redis instances: the scheduler must publish to the same broker the worker consumes.

Place real connection credentials (not in Git) in `backend/.env.notifications` using `backend/.env.notifications.example` as a template; this secret file is Git-ignored. Configure a genuine production Supabase pooler URL, the production Django secret, the same broker/result backend as the web app, authenticated SMTP sender, and private S3 storage credentials for invoice archival. Pin filesystem permissions: `chmod 600 backend/.env.notifications`. Never print the file in logs or expose Redis credentials.

### Startup on the already-existing Docker host

First complete **real production Supabase backup + isolated restore**, apply Django migration `0017_liveclass_recipient_notifications` through the approved backend release, and verify `django_migrations`. Once the external broker and SMTP credentials are securely configured:

```sh
cd Amaris-Mathematics-Academy
cp backend/.env.notifications.example backend/.env.notifications
# Edit backend/.env.notifications securely and restrict its access.
chmod 600 backend/.env.notifications
docker compose -f backend/compose.notifications.yml config --quiet
docker compose -f backend/compose.notifications.yml build
docker compose -f backend/compose.notifications.yml up -d --no-build
docker compose -f backend/compose.notifications.yml ps
docker compose -f backend/compose.notifications.yml logs --tail=80 notification_worker celery_beat
```

The two startup preflights validate migration `0017`, Postgres, TLS Redis, queues and SMTP login before Celery starts (no test mail is sent). The shell checks must be run **on the intended permanent host**, not in GitHub Actions or an ephemeral session; no host is provisioned here. Prevent automatic restart of old duplicate Beat processes.

Finally, perform a real PayFast **sandbox** booking with synthetic tutor and student records and confirm actual delivery to three inboxes (student, tutor, admin). Check PDF invoice and the 30-minute reminder. Use Celery's queue-specific healthcheck, logs and database delivery timestamps; SMTP handshake alone does not prove that an inbox received a message.

**Deployment status:** only configuration and CI tests are committed on draft PR #336. No Docker daemon was accessed, no external Redis allowlist changed, no paid Render service created, and no production payment/SMTP delivery verified.
