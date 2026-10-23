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

## Render provisioning and live-worker verification

The dedicated `render-notifications.yaml` defines only these **two paid Starter background-worker services**: `amaris-production-notification-worker` and `amaris-production-beat`. It references the **existing** `amaris-production-web` Django application and `amaris-production-broker` Redis key-value store, without configuring or duplicating them. Use **Render Dashboard → New → Blueprint**, select this repository and production release branch, and set the Blueprint file path to **`render-notifications.yaml`**. Review the preview carefully: only these **two** worker services should be newly created, with no production web/Redis changes. Review and approve the additional Starter plan charges before selecting Apply. Do **not** sync the repository-wide `render.yaml` for this task; it also declares other production resources.

A repository YAML declaration does not mean the workers are running. The available Render connector can inspect and redeploy *existing* workers, but it cannot create background workers or trigger a Blueprint sync. Do not treat Blueprint creation or a green GitHub test as proof of successful real email delivery.

The notification worker uses the `notifications` Celery queue. Beat is the *only* scheduler and publishes the existing 30-second booking-confirmation and 60-second booking-reminder jobs. The production Redis broker `amaris-production-broker` already exists; never create an additional one.

Before a worker or Beat instance accepts jobs, `python ops/check_notifications.py --role notifications` or `--role beat` verifies the production connection, applied migration `0017`, broker reachability and routing. The notification worker additionally authenticates to SMTP without sending a message. A non-zero result prevents Celery startup, rather than falsely reporting that emails are being processed.

Configure the following **on the production Django web service**, in its secured Render environment, so the Blueprint can inherit them without duplicating secret values: `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, and `DEFAULT_FROM_EMAIL`. Confirm `EMAIL_PORT=587`, `EMAIL_USE_TLS=true`, and `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`. The Blueprint resolves the four shared values with `fromService`; do not store credentials in GitHub files or show them in logs. If a required web environment value is missing, create it there before syncing. Optionally set `BOOKING_ADMIN_NOTIFICATION_EMAILS` on the notification worker for additional managed staff inboxes.

The rollout order remains: (1) verified genuine production Supabase backup and isolated restore, (2) successful backend CI and staging sandbox three-inbox acceptance, (3) merge backend PR and verify Django migration `0017`/production readiness, (4) provision and verify notification worker plus a **single** Beat instance, (5) inspect Render worker and Beat logs and Celery queue health, (6) merge/deploy live-students frontend PR, (7) verify a new sandbox-origin booking's three recipient emails and 30-minute reminder. Never send a real-money production payment merely to test delivery.

Verification must distinguish an SMTP handshake from actual inbox delivery: check that the worker reports registered notification tasks, that Beat schedules them, that one verified synthetic booking produces distinct student/tutor/admin receipt timestamps, that a duplicate callback produces no additional email, and that the messages really appear in all three inboxes. Monitoring-only workers and passing synthetic CI restore tests are not substitutes.
