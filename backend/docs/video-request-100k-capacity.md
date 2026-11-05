# Amaris Mathematics Academy: 100,000+ student video requests

**Draft implementation in PR #432. Do not deploy without the release gates below.**

## What 100,000+ means

This implementation targets **more than 100,000 distinct registered students**
and persisted individual video-request orders in PostgreSQL. The isolated
PostgreSQL test fixture creates **100,001 students and 100,001 paid request
records**, then submits another valid checkout for the 100,001st student.

This does **not** prove 100,000 requests at the same second, 100,000 video
uploads at once, 100,000 finished videos, or guaranteed tutor delivery dates.
Live traffic throughput needs representative load testing and scale budgeting.

The requested simultaneous-submission acceptance target is now **50,000**.
The small 16-thread regression test is only a CI smoke check. The new
[50,000-submission runbook](../load_tests/VIDEO_REQUEST_50000.md) defines
distinct identities, distributed synchronized multipart checkouts, measured
client concurrency, preserved latency/error gates and separate server evidence.
That target is **NOT RUN / NOT VERIFIED** against Amaris until hosting,
test accounts and monitored load generators are available. Offline harness
contracts and loopback mock results do not establish production capacity.

The tutor video-production capacity is independent from web checkout capacity.
The existing queue ETA default is only **two videos per day** unless a
different `VIDEO_REQUEST_DAILY_CAPACITY` value and sufficient tutors are
actually configured. Do not accept unbounded paid demand without confirming
fulfilment capacity, published terms and meaningful delivery expectations.

## Existing workflow and improvements

1. A verified student selects programme, subject, level, topic, video
   package, duration and instructions and uploads required documents
   (Django validation in draft PR #385).
2. Django validates the documents, writes a VideoRequest with a unique
   idempotency key and stores the documents privately. PostgreSQL
   transaction-scoped advisory locks serialize **the same checkout key**
   without locking other students' keys.
3. PayFast checkout charges the server-owned package price. A genuine
   verified PayFast ITN puts the request into the paid production queue,
   assigns an invoice number and ticket and schedules confirmation.
4. Indexed paid-queue lookup supports priority/FIFO ordering, and stable
   timestamp+UUID tie-breaking prevents two requests both being first.
5. Student dashboards fetch bounded request pages (default 100, maximum 100);
   unchanged consumers still receive an array. If more history exists, follow
   the `X-Next-Created-At` and `X-Next-Id` response headers with query
   parameters `before_created_at` and `before_id`.
6. Queue position is computed once per response rather than recalculated
   for its estimated-ready date. The notification worker selects the real
   queue head instead of scanning and recounting up to 25 candidates.
7. Online PostgreSQL indexes are added in migration 0017 using
   `CREATE INDEX CONCURRENTLY`. Back up and audit migration readiness before
   applying them to any shared database; index building consumes I/O.

## Attachment and storage limits

The currently selected video backend permits five PDFs/JPEGs/PNGs, at most
10 MB each, and **25 MB total**. Request bodies pass through the frontend
proxy and Django. Simultaneous large uploads can exhaust temporary disk,
network connections and memory even with 100k-record database support.

The separate **1 GB upload** changes in PRs #337 and #338 are **not merged**,
and the prior Supabase bucket inspection reported a 50 MiB object limit.
Do not promise 1 GB or 100,000 concurrent uploads until the Supabase project,
private bucket settings, quota, signed direct-upload protocol, virus/content
checks and end-to-end retry behavior have been verified.

## Acceptance and release gates

- CI: Django Black/Ruff, OpenAPI validation, migrations, existing video
  tests, signed sandbox checkout, 100,001 synthetic student/request fixture,
  owner-only history, priority order, and concurrent same-key idempotency.
  Tests use a disposable PostgreSQL instance and mock/no live payments.
- Stage the companion frontend mandatory-field validation (PR #384) and
  complete a genuine PayFast **sandbox** checkout. Check verified callback,
  a single ticket and invoice using the existing Amaris branded template,
  private PDF archive, confirmation messages, correct status pages and
  retry semantics.
- Load-test **isolated staging** at defined arrival rates (for example
  10, 50, 100 requests per second) and measure p95/p99 response time,
  error rate, Postgres locks, connection count, Celery queue latency, mail
  quotas, file storage throughput and callback processing. These are test
  scenarios, not certified production numbers.
- Check 100k saved requests in Django Admin/tutor queue. Confirm tutor
  capacity, fairness, financial reconciliation and student expectations
  before opening sales at that volume.
- Tune PostgreSQL connection pooling, Render instances, Redis/worker
  concurrency and external-service quotas based on results, not guesses.
  Any new paid service or plan upgrade requires separate approval.
- Verify encryption, student-only access, retention and document deletion;
  never expose student documents or videos through public URLs.
- Make a recoverable database/storage backup, confirm rollback, pass
  frontend and container security gates, and obtain explicit approval
  before production deployment.

## Known dependencies / blockers on 5 November 2026

- PR #432 is stacked on draft backend PR #385; the frontend form companion
  PR #384 is also still draft. Don't apply this to GitHub `main`: the
  Render live backend is on `production-release-20260923`.
- Connected Render inspection reported the production backend, live student
  frontend and staging backend suspended for billing, so real staging/live
  request acceptance is unavailable until the account is restored.
- No student records, real videos, messages or payments were created in the
  production database by this work; no deployments or billing changes.

