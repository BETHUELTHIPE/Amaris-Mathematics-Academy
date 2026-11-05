# Amaris live-class booking capacity: 100,000+ students

**Status:** Draft PR #431. This does NOT declare production-ready capacity.

## What the 100,000+ target means

There are three separate limits:

1. **Registered students:** >100,000 distinct student accounts can access the
   site and request a booking. The CI fixture creates 100,001 synthetic accounts
   and completes a checkout for the 100,001st account.
2. **Total paid bookings:** The PostgreSQL booking table is not limited to
   100,000 records. A session still requires a unique available tutor slot and
   verified payment. Large booking-history totals require controlled retention,
   backup, and query-plan checks.
3. **Simultaneous requests:** 100,000 people pressing Book at the *same second*
   is NOT proven by an account-count test. That requires a separate load test,
   production-sized infrastructure, gateway and SMTP quotas, and explicit cost
   authorization. We must not promise this concurrency level without evidence.

For one-to-one Zoom lessons, an available tutor must exist for each requested
date and time. Software throughput cannot create tutor availability.

## Architecture and safeguards

- **Django/DRF + PostgreSQL:** Supabase student identity is mapped to
  StudentRecord. UUID identity and email are unique. Booking reference,
  idempotency key, and a conditional unique active reservation for each tutor
  slot prevent duplicate holds.
- **Short row locks:** Checkout locks only the selected tutor slot, not the
  shared tutor user record. Different tutor slots can be reserved concurrently.
- **Read-only availability:** GET requests do not run a global expired-hold
  UPDATE on the booking table. Instead a correlated EXISTS excludes confirmed
  bookings and unexpired holds. Expired holds stop hiding availability
  immediately; Celery Beat cleans them up independently.
- **Keyset paging:** GET /api/v1/live-classes/slots/ accepts
  programme/subject/level, limit (1..100), and after_start + after_id.
  This lets students browse times without expensive high OFFSET scans.
- **Grade/level discovery:** GET /api/v1/live-classes/levels/ returns available
  grade/level choices for a programme and subject, regardless of which times
  are in the first 100 entries.
- **Verified payment:** Only valid, independently verified PayFast callbacks
  confirm bookings. A callback rechecks the hold and status after locking that
  booking row, rejecting expired/cancelled or replayed sessions.
- **Notifications:** Celery notification worker processes bounded batches
  (default 25 messages per dispatch; configurable 1..100), each inside its
  own row lock/transaction. A scheduler normally dispatches every 15 seconds.
  Actual throughput is bounded by SMTP latency/quotas and worker count.
  Failed jobs must be monitored for retry/duplicate acceptance risk.
- **Database indexes:** Indexed provider reference for replay detection and
  a partial index covering unemailed confirmed bookings. Existing slot,
  student, hold and conditional unique indexes remain intact.
- **Existing behavior:** PayFast amounts remain server-set at R250 per hour
  in the current main branch. Email/invoice flows stay unchanged; PR #431
  does not merge the separate WhatsApp feature or the unmerged rescheduling PR.

## Tests and release acceptance

- CI regression: 100,001 synthetic students, final student's checkout; one
  slot with two concurrent competing students; a single active hold;
  read-only availability for expired holds; keyset pagination; grade/level
  beyond first 100 tutor slots; multiple confirmation/reminder emails per task
  with no duplicates.
- CI gates: Black, Ruff, mypy, PostgreSQL migrations, OpenAPI, Django
  regression and integration, frontend lint/typecheck/build, accessibility,
  responsive E2E, Lighthouse, secret/dependency scan, Docker image scan.
- Isolated staging: load at least 100,001 student identities and realistic
  tutor slots. Benchmark p50/p95/p99 booking requests and GET availability,
  database lock waits, connection saturation, CPU/memory, queue lag and
  callback processing. Run burst tests on *different* slots and contention
  tests on the *same* slot.
- End-to-end paid session: genuine PayFast **sandbox** payment -> verified
  Django confirmation -> one enrolment/booking record, original professional
  PDF invoice archival, confirmed student/tutor/admin emails and scheduled
  reminder. Verify timeout and duplicate callback behavior.
- Test account security: do not import 100k synthetic accounts into any
  production or customer-connected Supabase authentication project. Never
  use real student phone numbers or PayFast live merchant credentials.
- Release operations: restore Render service and broker availability; check
  staging workers and exactly one Beat; verify PostgreSQL pool limits, SMTP
  quotas, hosting budget, rollback/backup, then obtain separate release
  approval before merging or deploying.

## Throughput illustrations (not guarantees)

At 100,000 completed bookings per month, average throughput is only
~0.039 bookings/second (30-day month), but real usage is bursty. You must
size for the **peak arrival rate**, not the average.

At the nominal 25 per batch and one dispatch every 15s, the *theoretical*
scheduler limit for either email type is up to 100 messages/minute before
accounting for SMTP latency, contention, retries and worker availability.
It does not certify 100,000 confirmations or reminders per day. Increase
worker capacity/rate only after an isolated staging benchmark and quota review.

**Operational blocker (2026-11-05):** the connected Render workspace reports
the staging and live services and staging Redis as billing-suspended.
This PR does not change billing, hosting or production.
