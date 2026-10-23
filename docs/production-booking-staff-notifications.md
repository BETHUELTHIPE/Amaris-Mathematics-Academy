# Amaris live tutoring: paid booking notifications (production backend)

The frontend booking change is a separate PR based on the live-student release branch. **Deploy this backend before the frontend**, because the new tutor selector requires `tutor_id` from `GET /live-classes/slots/`.

## API and recipients

- `GET /live-classes/slots/?tutor_id=<id>` optionally limits availability to a tutor with published free slots. The response includes `tutor_id`, not the private Zoom link.
- The existing server-side PayFast verification, R250 per hour, 1–24 whole-hour sessions, booking holds, ownership permissions and 30-minute reminders remain in place.
- Only after payment is provider-verified and the booking is **confirmed** does the existing notification worker email the student with PDF invoice and Zoom link, the selected tutor with full booking details, and Django administrators with full booking details.
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
6. Perform one isolated real PayFast **sandbox** payment callback with synthetic student data; verify the student, tutor and admin inboxes each received the correct email, and that only the student got the PDF invoice. Retry the worker and ensure no duplicate invoice. Never use live money for acceptance.
7. Confirm the notification worker and scheduler are running; test the 30-minute student reminder, staged shutdown and retry.
8. Deploy backend, verify runtime SHA, migrations, HTTP smoke checks and error logs; only then release the separately tested frontend PR. Keep the previous production backend SHA as rollback target, and stop if schema compatibility or SMTP is unresolved.

**Current state:** Code prepared in a draft PR only. No production database changes, actual payments or external confirmation emails were performed.

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
