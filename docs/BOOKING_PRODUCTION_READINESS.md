# Live class booking production readiness

Status on 2026-09-30: **blocked**. Do not direct students to a live PayFast checkout until every release gate below is complete.

## Workflow and controls

The booking UI offers CAPS, IEB, TVET and University; Mathematics and Mathematical Literacy; a grade or level; a topic; and an available one-hour tutor Zoom slot. The API fixes the amount at R250. A checkout attempt holds one slot for 30 minutes and uses its own PayFast reference. The browser return never confirms a booking: only a server-verified ITN can do that. Confirmed students see the Zoom URL; the confirmation email includes class details and an invoice attachment. A scheduled reminder sends the URL near 30 minutes before start.

This change aligns numeric slot IDs between availability and checkout, makes each checkout attempt retain a distinct payment reference, records a verified charge that arrives after a hold expires as `payment_review`, and drains multiple pending confirmations/reminders per scheduler tick. A `payment_review` booking releases no Zoom URL and must be resolved by staff as a replacement class or refund. The booking page reports API outages separately from no available tutor slots.

## Current deployment blockers

1. The production Django service `amaris-production-web` (`srv-dapn6b3tqb8s73d3r7n0`) failed its latest deployment during `migrate`: SQLite received the PostgreSQL-only `sslmode` option. The configured production Postgres database exists, but the deployed web service appears to lack a usable `DATABASE_URL` binding. Confirm the environment binding in Render without copying the connection string into logs or a PR. The code now fails early with a clear missing-URL error when `DJANGO_DEBUG=false`.
2. The confirmed Render workspace lists no Celery workers or beat service. `render.yaml` declares a critical worker, notification worker and beat, but the actual production services do not include them. Until these run against the production broker and database, confirmation emails, invoice attachments and 30-minute reminders cannot be guaranteed. The production Postgres and broker already exist; provisioning workers is a separate recurring-cost decision.
3. The live student frontend is deployed from `render-live-current-20260918`, which does not include this booking route. The main/staging code must be promoted only after backend and worker readiness. Do not expose a booking navigation link to a missing route.
4. Live PayFast settings (merchant credentials, HTTPS return/cancel/ITN URLs, verified source IP handling) and SMTP delivery have not been observed end to end. The present code validates configured live HTTPS URLs, but an actual PayFast sandbox transaction, callback, confirmation message/invoice and reminder still require a connected staging setup. A live payment should occur only after those checks and explicit authorization for its charge.
5. The production database's empty external IP allowlist prevented read-only schema inspection through hosted Render MCP. Check migration `content.0007_live_class_booking` before serving availability, and apply `0008_liveclass_payment_review` as part of the release. Do not open the database to public IPs merely for this check.

## Release sequence

1. Review and merge this change. Keep the production booking navigation disabled until the final step if the live branch exposes it earlier.
2. Bind `DATABASE_URL` from `amaris-production-postgres` to the production web service, confirm `DJANGO_DEBUG=false`, run migrations, and require the `/health/ready/` endpoint to pass. Confirm the API can read actual seeded tutor slots with valid one-hour times and Zoom URLs.
3. Start the beat and notification worker with the same database, broker and SMTP configuration as the web service; verify task registration and periodic runs, queued email delivery and retry behavior. Monitor `payment_review` in Django admin and assign staff to contact affected students promptly.
4. On staging, run an authenticated student journey with an actual PayFast sandbox callback: available numeric slot ID → R250 checkout → verified `COMPLETE` ITN → confirmed status and Zoom link → one confirmation email with invoice → one reminder in its 30-minute window. Exercise duplicate ITN, a rejected amount, expired hold and second student's slot isolation. A browser redirect alone must never confirm a booking.
5. Deploy the backend, worker and beat release together, then promote the frontend and confirm the route, slot list, checkout, return page and site navigation. Review callback and email logs without leaking token, URL secret or personal information. If a release check fails, disable booking navigation and roll back the frontend; preserve payment/booking records and reconcile any gateway charges before another attempt.

## Local verification

`python manage.py test content` — 80 tests passed, 3 skipped after collecting static files. `python manage.py makemigrations --check --dry-run` — no changes. Ruff, `git diff --check`, frontend TypeScript typecheck and the booking contract tests passed. These tests use a mocked PayFast verifier and local email backend; they do not establish production readiness on their own.
