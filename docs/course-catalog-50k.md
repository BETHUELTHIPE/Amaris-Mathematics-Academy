# Amaris course catalogue: 50,000+ individual courses

**Release stage:** draft PR #430, no production or staging deployment.

## Scope and distinction

This feature is for **more than 50,000 different course products (SKUs)**.
It is not a certification for 50,000 concurrent visitors, payments per minute,
video streams, or courses automatically uploaded. Those have separate capacity,
payment-service and storage limits.

Django already stores courses as PostgreSQL records with unique slugs and
per-course server-authoritative prices. There is no hard count limit of 500 or
50,000 course records in the model.

## How the course store handles 50k+

- Public API: `GET /api/v1/courses/?page=N&page_size=24`, with default
  page size 24 and server-enforced maximum 48.
- Full-database search: `?search=calculus` (title, summary, curriculum and
  level) and server-side programme filtering `?programme=CAPS|TVET|University`.
  Search is never restricted to the initial page.
- Stable default ordering (order, title, primary key) and direct page jumps
  in the frontend allow reaching the last page of a 50k+ catalogue.
- Course detail: `GET /api/v1/courses/<slug>/`; checkout still uses slug
  lookup and the server's price, not a client-submitted price.
- Lesson totals: correlated aggregate subquery avoids joining/grouping
  the full course catalogue before LIMIT/OFFSET and counting.
- Homepage featured query returns at most six results, independent of page 1.
- Admin shows 50 results per page and avoids an additional full-result
  COUNT when displaying search/filter results.
- Draft/review/archived or not-yet-published courses are excluded from public
  browsing and checkout remains limited to published courses.
- When a configured CMS API is unavailable, the public catalogue shows a
  temporary-unavailable message instead of selling hard-coded sample courses.

## Automated proof

The new `content.test_course_catalog_50k` Django test creates **50,001**
synthetic published courses in PostgreSQL in batches, then checks:

1. Last paginated page (page 2084) returns the final nine courses and
   total count 50,001, without truncation.
2. The final course is searchable across all pages.
3. Its detail endpoint resolves and a PayFast sandbox checkout can be
   constructed at the server-owned price.

The earlier 601-course suite remains and checks search/filters, no drafts,
repeated verified-payment idempotency, invoices and enrolments. Tests do not
send a live payment or import courses into the user's production database.

## Operator gates before production

1. Check PR CI: Django formatting, lint, typecheck, migrations, 50,001-course
   tests, frontend build, Lighthouse, accessibility, security and browser
   automation. All required jobs must pass on the final commit.
2. Benchmark search latency, request memory, pagination and database query
   plans using `EXPLAIN (ANALYZE, BUFFERS)` against an isolated staging
   dataset with at least 50,001 courses. Record p95 for title/summary searches,
   last-page loading, and detail/checkout. Never run heavy load tests on the
   production database.
3. If search p95 is too slow, plan PostgreSQL `pg_trgm` GIN indexes on the
   searched fields with a database administrator. Verify the extension/schema
   and permissions in the actual managed PostgreSQL provider first; do not
   enable extensions or run blocking index migrations blindly in production.
4. Verify sample content upload workflows, category selection, publication
   permissions, and CMS cache invalidation. This PR does not introduce a
   bulk-CSV uploader; importing 50k actual courses is a separate operation.
5. Complete a **real PayFast sandbox payment** on a high-numbered published
   course and confirm a single paid enrolment, the correct existing branded
   invoice, email delivery and private resources.
6. Verify database backup, rollback, storage bandwidth, Redis/Celery and
   actual hosting service health before any controlled release.
7. Verify scaling of orders, email jobs, video delivery, student dashboards,
   student authorisation and payment callbacks separately for high
   transaction concurrency.

**Known blocker 5 November 2026:** Render workspace lists production and
staging frontend/backend services and Redis brokers as suspended due to
billing. No staging/browser production acceptance is possible on those
services until account-level restoration. No deployment or billing changes
are authorised by this PR.
