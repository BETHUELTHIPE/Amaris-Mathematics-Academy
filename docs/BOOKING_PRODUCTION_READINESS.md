# Live class booking production readiness

Status on 2026-10-07: **release candidate**. The application path is implemented, but production must remain closed until the staging payment and delivery gates below pass and the required workers are running.

## Staging route verification on 2026-10-07

The deployed staging frontend at `f27e7fc1f1439f09aa4b551b2a251b8f8740016a` returns HTTP 200 for `/book-online-live-class` with programme selection, available Zoom slots and R250 pricing. A cold request took 54.86 seconds; Render runtime logs show startup after the earlier acceptance test's 30-second timeout. React also serializes an unused not-found boundary into the page's script data, so matching all response bytes for 404 text rejects a valid page.

Both staging workflows now use a shared bounded route check: up to four 30-second attempts with five seconds between transient failures. It still requires HTTP 200 and the rendered booking content, and immediately rejects an actual 404, HTTP 500, missing content or incorrect pricing. These checks verify route delivery only; no authenticated checkout, PayFast sandbox payment, invoice delivery or reminder has been accepted by this observation.

## Production contract

- Students choose CAPS, IEB, TVET or University; Mathematics or Mathematical Literacy; level, topic, tutor and an available one-hour Zoom slot.
- The API owns the price (R250), holds one slot for 30 minutes and prevents overlapping pending or confirmed bookings.
- A browser redirect never confirms a booking. Only a signed, server-verified PayFast ITN with the expected merchant, amount, student and booking reference can confirm it.
- A verified payment received after the hold has expired moves to `payment_review`; it never releases a Zoom link and must be resolved by staff.
- Confirmed students receive one confirmation email with a PDF invoice, an authenticated owner-only invoice download and a reminder near 30 minutes before class.
- Public availability never exposes Zoom URLs. Zoom links are released only on an authenticated confirmed booking.

## Release architecture

`render.yaml` matches the existing `amaris-production-web` Python runtime and declares the web service, critical worker, notification worker, beat scheduler, broker and cache. Production deploys are manual. The web service runs migrations as a pre-deploy command and serves `/health/ready/`; notification and scheduler processes use the same database and broker.

The production database is Supabase Postgres project `epkcuseloinygkakxxdu`. Existing Django data is in `public`, so the release keeps `DATABASE_SCHEMA=public` to avoid a destructive schema cutover. The backend tables must retain the applied deny-all Data API hardening (RLS enabled and API-role access revoked). Do not expose service-role or S3 credentials to the browser.

The live student origin is `https://amaris-mathematics-academy-live-students.onrender.com`. PayFast return, cancel and ITN URLs use this origin and `https://amaris-production-web.onrender.com`; URL construction accepts either a backend origin or an `/api/v1` base without duplicating the API prefix.

## Remaining deployment gates

Inspection on 2026-10-07 confirms that the production broker and cache exist, but no critical worker, notification worker or beat scheduler is provisioned. Supabase has applied `0007_invoice_pdf_archive`, but neither booking table exists. The candidate now retains that invoice migration and its metadata/recovery behavior, merges it with booking migration history, and includes a PostgreSQL migration to keep the new booking tables private from Data API roles. No confirmation/reminder evidence was found in the connected test inbox. The Render connector cannot create background workers or change existing service source branches/build configuration; completing these operations requires Dashboard access.

1. Back up Supabase before migration. Confirm the target without logging credentials, then apply migrations and verify `content_tutoravailabilityslot` and `content_liveclassbooking` exist alongside the current data.
2. Configure private production secrets: Supabase session-pooler `DATABASE_URL`, Auth publishable key, S3 keys, PayFast merchant values and SMTP credentials. Keep both Supabase buckets private.
3. Provision and start `amaris-production-critical-worker`, `amaris-production-notification-worker` and `amaris-production-beat`. These are recurring-cost Render services and require explicit approval before creation.
4. Seed only real, reviewed one-hour tutor slots with tutor name, future start/end time and a valid Zoom URL.
5. On staging, complete one PayFast sandbox journey using synthetic student data: slot → R250 checkout → verified `COMPLETE` ITN → confirmation → invoice archive/download → reminder. Also verify duplicate ITN, bad amount, expired hold and a second student's slot isolation.
6. Promote backend, workers and scheduler together. Verify readiness, queue consumption and email delivery before promoting the frontend route. No live charge is permitted as a release test.

## Rollback

If any gate fails, hide the booking navigation and roll back the frontend and application services. Preserve booking/payment records, stop new checkouts, and reconcile every gateway callback before retrying. Database migrations for payment records are not reversed during an incident unless a reviewed restore plan requires it.

## Local verification

The release gate includes Django tests and migration drift, Python formatting/lint/type checks and dependency audit, frontend unit/build/type/lint checks and dependency audit, the production architecture contract, and validation of `render.yaml` against Render's official schema. Local tests use mocked PayFast verification, isolated storage and a local email backend; they do not replace the staging sandbox journey.
