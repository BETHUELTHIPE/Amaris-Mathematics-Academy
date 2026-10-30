# Amaris 30-day tutor activity and earnings statement operations

## Scope and semantics

Each tutor with an active academy tutor contract or approved Tutors group receives one private A4 PDF for each contiguous **30-day** period. The first cycle covers the previous 30 complete days in South African time; thereafter each period is contiguous and non-overlapping. This is not necessarily a calendar month. Beat checks for due statements once daily, then the notification queue retries archived statements every 5 minutes until the tutor and administrator copies are both recorded as sent.

A statement includes distinct students served (no names/emails), completed paid Zoom classes, taught hours, paid tutor-assigned student video requests, ready videos, verified gross sales, contract-snapshot tutor/academy split, held/eligible amounts and **only provider-confirmed** bank payouts. Reversed transactions are not shown as earned. **Never present a statement as a payment receipt.** The separate provider-confirmed `TutorPayout` and proof-of-payment flow remains authoritative; reports do not initiate payouts.

## Records, privacy, and backups

The additive migration `content.0019_tutor_activity_statements` creates a private relational snapshot, a deterministic report key, SHA-256 PDF integrity hash, and independent tutor/admin email timestamps. The A4 PDF reuses the academy's existing branded logo and letterhead. The object is saved under `tutor-statements/<year>/<tutor-id>/<statement-reference>.pdf` using Django's **default storage**, which must be configured for the private production **Supabase admin bucket `amaris-cms-files`**. If there is no protected S3 configuration, the job fails closed. The Django Admin **Tutor activity statements** view is superuser-only; files are streamed from server storage via a secured admin endpoint, never by publishing object URLs.

Do not copy student names, phone numbers, email addresses, Zoom links, banking account numbers, provider credentials or authentication tokens into report content or logs. Only students' distinct count is exported.

## Existing services, configuration, and deployment

- Existing Django backend, notification worker and Celery Beat; no paid new services.
- Required: private Supabase S3 credentials and `SUPABASE_S3_ADMIN_BUCKET=amaris-cms-files`; existing SMTP `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`.
- Recommended: `TUTOR_STATEMENT_ADMIN_EMAIL` set to the official administrator inbox. If omitted, it defaults to the existing SMTP account email address.
- `create_due_tutor_statements` runs every 86,400 seconds on the notifications queue, with a maximum of 500 newly issued statements per run; the cursor scans all tutors to avoid starvation.
- `deliver_due_tutor_statements` runs every 300 seconds, tries up to 50 pending statements and updates **each recipient** timestamp separately. Repeated deliveries avoid already stamped roles. SMTP cannot guarantee exactly-once on process failure after sending but before DB commit; investigate such ambiguous cases in the email provider before manually retrying.
- Notification-only Beat installations include both new tasks. Do not run multiple Celery Beat instances against the same Redis broker and database.
- Before migration, take one retained encrypted production Supabase backup with restore proof, verify the staging project isolation and private storage bucket, and deploy the tested backend revision with a rollback plan. Do not run migrations against the wrong project or send initial statements to real tutors without an approved acceptance plan.
- The first scheduled production run can create and email the prior 30-day report immediately; set `CELERY_BEAT_SCHEDULE` rollout accordingly and verify a sample dry run and staging SMTP inbox first.

## Acceptance

Run `python manage.py makemigrations --check --dry-run`, `python manage.py migrate --noinput`, `python manage.py test content.test_tutor_statements`, black, ruff, mypy, full backend regression suite; then verify a single genuine staging tutor, administrator recipient inbox, both exact PDF attachments, correct private object path, admin download, no duplicate emails under retry, verified payment totals and protected bucket permissions. Production is **not ready** until these gates pass.
