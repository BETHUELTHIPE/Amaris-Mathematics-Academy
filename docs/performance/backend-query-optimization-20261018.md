# Backend query optimization — 18 October 2026

Base: production backend branch `production-release-20260923`, commit
`eafb37db6cfb20a9bf84a0ec4698b5e6af10fae4`. Render connector confirmed this
commit is live on `amaris-production-web` when inspected. This change has not
been deployed.

## Changes

- Tutor dashboard: annotate each slot with `EXISTS` instead of prefetching full
  booking records and querying reservations again per slot. The dashboard keeps
  four view-level queries regardless of list length; authentication is excluded.
  Write responses still check current reservations directly. Preserve all
  existing reservation statuses, ownership checks, private data handling, the
  120-row limits, and whole-account summary counts.
- Public slots: one correlated `EXISTS` checks a confirmed booking or an active
  pending hold. Status and hold expiry now refer to the same booking, so an
  unrelated cancelled booking's future expiry cannot block a stale hold.
  Browsing remains read-only; locked checkout and scheduled expiry own writes.
  Preserve chronological ordering, the 100-slot cap and private Zoom URLs.
- Course catalogue: port the correlated published-lesson count from PR #257 onto
  the current production base. Avoid the outer lesson join, DISTINCT count and
  GROUP BY for paginated course reads. Preserve existing lesson visibility/count
  rules, public API fields, filters, detail prefetches, and response caching.
  Public availability work is adapted from #254; that production base already
  removed writes from public GET.

No model/schema migrations, dependency changes, infrastructure changes or paid
resources. Existing public cache namespaces and private-response policy remain
in place.

## Observed verification

Python 3.13.15, Django 5.2.17, isolated in-memory SQLite with synthetic identities:

| Scenario | Before | After |
| --- | --- | --- |
| Tutor view, one slot | 6 queries | 4 queries |
| Tutor view, twelve slots | 17 queries | 4 queries |
| Tutor view, 125 slots (120 returned) | Not measured | 4 queries; summary 125 |
| Public slots, twelve slots | Not measured | 1 SELECT; no private link |
| Course list, twelve courses | Not measured | 2 queries; cached repeat 0 |
| Featured courses | Not measured | 1 query |
| Course detail with modules/lessons | Not measured | 3 queries |

The tutor query-budget tests failed against the unchanged base (6/17 queries),
then passed after the implementation. Counts include response rendering but not
external authentication/network calls. These are query-count results, not
production latency or concurrency measurements.

Run local regression from `backend/` after `python manage.py collectstatic
--noinput`: `python manage.py test --noinput`. Formatting, Ruff, mypy (36 source
files), Django deployment checks, OpenAPI validation and migration-drift checks
also pass locally. Existing CI must verify PostgreSQL 17 and the release gates.

## Release and rollback

Open a PR against the production backend branch. Do not merge or deploy until
required checks pass and staging acceptance/production promotion are authorized.
After staging, measure uncached/cached catalogue latency, tutor dashboard latency,
slot availability and error rates using synthetic accounts. Do not infer speed
or capacity from query count alone. Render's inspected one-hour production
metrics had no HTTP latency series, so no production p95 improvement is claimed.

Rollback is application-only to the previous verified commit; no database schema
or data rollback is required. Production remains on the base until an explicitly
approved release.
