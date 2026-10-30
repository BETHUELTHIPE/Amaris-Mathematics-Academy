# API query efficiency

Public content, course outlines and tutor dashboards retain their existing response fields, authentication, filters and response shapes. Course pagination remains 24 items per page. Public page-cache lifetimes and financial write paths are unchanged.

## Measured changes

Cold requests against isolated synthetic SQLite fixtures produced these database query counts. The tutor fixture uses an authenticated synthetic principal, so its counts cover view/serialization database work and exclude Supabase authentication and network overhead. The same query budgets run against disposable PostgreSQL in CI.

| Endpoint / workload | Before | After |
| --- | --- | --- |
| `/api/v1/bootstrap/`, 12 published announcements with media | 15 queries | 4 queries |
| `/api/v1/tutor/dashboard/`, 120 slots and mixed booking states | 125 queries | 4 queries |
| Course list | 2 queries, pagination count joins and groups lessons | 2 queries, pagination count reads courses only |
| Course detail, 5 published lessons | 3 queries, including full private lesson bodies | 3 queries, lesson bodies excluded from database reads |

Bootstrap batches announcement media in one prefetch. Tutor slot reservation checks use a correlated `EXISTS` in the slot query instead of issuing an extra query per slot or loading entire booking collections. Write endpoints retain fresh reservation checks and transaction locks.

Course lesson counts use a correlated subquery for returned courses, so pagination does not aggregate the entire matching course/lesson join. Zero counts and the existing publication-time predicate are preserved. Public course outlines still contain only summary fields; their queries now defer the unused private lesson bodies.

All tutor API responses, including rejected authentication, explicitly use `Cache-Control: private, no-store` and vary by authorization. No tutor or student response is added to a shared response cache.

## Verification

From `backend/`, with disposable database and cache configuration:

```sh
python manage.py test content.test_api_performance content.test_tutor_dashboard content.tests.PublicContentApiTests content.tests.PermissionTests
```

The query tests disable the public page cache so cache hits cannot hide repeated database access. They verify publication boundaries, private lesson-body exclusion, existing pagination/search/featured response shapes, reservation states, unreserved slots, authentication failures and suppression of unpaid students' contact details.

These measurements establish query-count and data-loading improvements. They do not establish production latency, throughput, maximum concurrent users or a percentage speedup. Hosted staging and representative before/after load tests remain release acceptance work.
