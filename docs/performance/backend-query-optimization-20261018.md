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

## Release verification follow-up

The original optimization commit `ad3b337cb2436cd70262cd587663eafda2582f29`
passed every applicable check in Quality Gates and Release run `39169071813`,
including strict desktop/mobile Lighthouse, browser E2E and container scanning.
Separate Payment Security and Backup Restore Verification checks passed too.
The restore check is CI recovery evidence, not a newly retained production backup.

Read-only Render binding preflight `39169608826` found that the actual staging
service uses the older, separate Render PostgreSQL database, while its directly
configured Auth and S3 endpoints still reference production Supabase. The new
requested staging Supabase project `atyhhjwwxgzeurnwayay` is healthy but has zero
public application tables. No deployment, migration, synthetic account/order,
upload, email or payment was attempted against these mixed bindings.

The follow-up startup fix accepts the **exact** dedicated staging Supabase direct
or session-pooler connection on port 5432, verifies database/role/schema over TLS
in a read-only transaction, and requires matching staging project, Auth and S3
endpoints before migration. Production, unrelated projects, transaction-pooler
port 6543 and mismatched schemas remain rejected. The older restricted-role and
separate Render checks remain intact. Three new regression cases bring the
offline release-contract suite to 23 tests. This adds no schema migration.

### Concrete staging configuration still needed

On the existing staging backend only, configure the following together using
credentials from **staging project `atyhhjwwxgzeurnwayay`**. Do not reuse production
credentials. The connector can apply configuration, but its current capabilities
do not retrieve the new project's database password or generate S3 access keys.

| Setting | Required value/source |
| --- | --- |
| `DATABASE_URL` | Staging project's session-pooler URI, port 5432, with its database password |
| `SUPABASE_PROJECT_REF` | `atyhhjwwxgzeurnwayay` |
| `SUPABASE_DATABASE_REQUIRED` | `true` |
| `DATABASE_SCHEMA` | `public` |
| `DATABASE_SSL_REQUIRED` | `true` |
| `SUPABASE_URL` | `https://atyhhjwwxgzeurnwayay.supabase.co` |
| `SUPABASE_PUBLISHABLE_KEY` | Staging project's publishable key |
| `SUPABASE_S3_ENDPOINT_URL` | Staging project's S3 endpoint from its Storage settings |
| `SUPABASE_S3_ACCESS_KEY_ID`, `SUPABASE_S3_SECRET_ACCESS_KEY` | Staging project's own S3 credentials |
| `SUPABASE_S3_REGION` | Region shown with those staging S3 settings |
| `SUPABASE_S3_ADMIN_BUCKET`, `SUPABASE_S3_STUDENT_BUCKET` | Two distinct private buckets in the staging project |

Keep all credentials in Render, outside GitHub code, PR descriptions and chat.
Verify private bucket identities/policies before upload tests. Align staging
frontend Auth and CMS URLs with staging too. Do not deploy the production migration
history into the old staging database: its migration history differs. The fresh,
separate staging Supabase database can apply the candidate's complete migration
history after the runtime identity guard passes. Existing Render staging data is
retained; do not fake migrations, drop tables or copy real student records.

### Current live HTTP baseline (before deployment)

GitHub-hosted runner, 18 October 2026 21:52:04–21:52:55 UTC (23:52 SAST),
production SHA `eafb37db6cfb20a9bf84a0ec4698b5e6af10fae4`:

| Route | Successful measured requests | Median TTFB | Sample p95 TTFB |
| --- | --- | --- | --- |
| Readiness | 12/12 | 877.61 ms | 1152.90 ms |
| Course catalogue | 12/12 | 218.93 ms | 240.98 ms |
| Public class availability | 12/12 | 915.57 ms | 1149.90 ms |

Two warmup requests per route were excluded. Calls were sequential and spaced by
0.5 seconds. Samples include DNS/TLS/network time and cannot isolate server SQL
duration. Twelve observations per route are a small sample, not a capacity test
or a representative production-user p95. Response bodies and user identifiers
were not retained. Raw observations are in `backend-live-baseline-20261018.json`;
workflow `39169708842` retains the artifact. This is a baseline only. Staging
acceptance and after-deployment improvement remain blocked by staging bindings.
