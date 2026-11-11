# Two-week student motivation email

One email becomes eligible 14 full days after `auth.users.created_at`, including
students who never opened a Django-backed page. The existing notification Beat
checks registrations every five minutes (100 per sweep) and delivers one queued
email per minute. This is a due-time threshold, not an exact-second guarantee;
backlogs and service outages can delay delivery. Existing eligible registrations
are included once on rollout.

Only confirmed email accounts with an existing `public.student_profiles` row
are considered. Deleted, banned, anonymous, explicit nonstudent app roles,
Django staff/tutor accounts, tutor applicants and inactive student records are
excluded. Tutors are excluded through recruitment and Django account records;
there is no reliance on user-editable role metadata.

Any recorded course, live-class or video payment excludes a student, including
refunds and paid bookings later cancelled. Active/completed enrollments also
suppress the message. Failed or pending checkouts do not count as payments.
Both the Supabase ID and historical email records are checked. Eligibility is
checked again at delivery so a payment made while queued suppresses the email.
Payments must be recorded in the application's payment tables; external payments
that have not been reconciled cannot be detected. A payment racing SMTP after
the final eligibility check cannot retract a message already being delivered.

## Deployment

- Apply Django migration `0019_student_motivation_email`. It only adds the
  private receipt table, enables RLS and revokes public Data API access.
- The backend database must be the same environment's Supabase database, with
  permission to read the required `auth.users` fields and
  `public.student_profiles`. No new frontend or service-role key is needed.
  Missing source tables or permissions fail closed, rather than falling back to
  Django's first-visit timestamp. Verify this with a synthetic staging account.
- Set `PUBLIC_SITE_URL` and `PUBLIC_API_URL` to this environment's HTTPS frontend
  and backend origins. These existing settings provide dashboard and opt-out
  links. Verify both links before enabling real delivery.
- Keep `STUDENT_MOTIVATION_EMAIL_ENABLED=true` (default). Set it to `false` to
  pause both queueing and sending. Restart the existing worker and singleton
  Beat with the release. Both tasks use the `notifications` queue, including
  when `CELERY_NOTIFICATIONS_ONLY_BEAT=true`.
- Existing SMTP settings send HTML and plain-text alternatives, with the academy
  contact as Reply-To. There are no charges or AI API calls for content.
- Restore suspended Render services and inactive Supabase projects before
  attempting staging or live acceptance. Do not clear billing suspensions by
  adding paid infrastructure.

## Delivery and preferences

Django Admin → Student motivation emails shows queued, sending, sent,
suppressed and review records, including registration, attempt, send and
unsubscribe times. These are read-only; deletion is disabled to retain the
one-email-per-account record. A database primary key prevents duplicate queue
entries; PostgreSQL row locks prevent concurrent claims. The claim is committed
before SMTP so an interrupted worker cannot automatically duplicate a message.

A sending record left after a crash, or a review record after an SMTP exception,
requires an operator to check provider logs before retrying. Do not blindly
reset these records: SMTP cannot guarantee exactly-once delivery across crashes.
`sent` means the backend accepted the message, not proven inbox receipt. Only a
safe exception class is stored; raw SMTP errors and recipient details are not
logged. Failed source/database operations are attempted by the next periodic
sweep. Uncertain sends do not retry automatically.

The signed unsubscribe URL shows a confirmation form. GET is read-only so email
link scanners cannot change preferences; a CSRF-protected POST saves the opt-out.
It affects motivation only; booking and invoice emails are unchanged. HTML
escapes profile names. Tokens contain a signed account identifier, no email.

## Staging acceptance

Use synthetic verified registrations with no payments, under and over the
14-day cutoff; test course/live/video payments and payment while queued. Verify
actual SMTP inbox receipt, both message formats, links, unsubscribe, Admin
receipts and repeat-task suppression. Do not alter real registration dates or
send campaign mail as a test. Production activation and inbox receipt remain
separate from local tests and CI.

## Local verification — 11 November 2026

- `python manage.py test content.test_student_motivation --noinput -v 2`: all
  18 tests passed on isolated PostgreSQL 16.2 with synthetic Auth/profile rows.
- `python manage.py test content amaris_cms tests --noinput -v 2`: 273 tests
  discovered; 270 passed, three Redis/Celery integration checks skipped because
  no Redis service was available. Admin assets were collected before this run.
- Black, Ruff, Mypy (41 source files), Django system checks and migration-drift
  checks passed. Python 3.12 was available locally; repository CI targets 3.13
  and PostgreSQL 17. CI and real staging SMTP acceptance remain separate.
- The existing booking-migration regression test now restores the latest
  migration leaves after its historical-schema assertions, preserving the new
  receipt table for subsequent transaction tests.
