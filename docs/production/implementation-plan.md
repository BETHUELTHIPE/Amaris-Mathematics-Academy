# Amaris Mathematics Academy Production Implementation Plan

Date: 2026-09-22
Production source branch: `production-20260922`
Live student site: `https://amaris-mathematics-academy-live-students.onrender.com`
Production API target: `https://amaris-production-web.onrender.com`

## Goal

Provision and verify a production Django/Celery data plane for real students without changing the live frontend until the backend passes all release gates.

## Production topology

- Django API: `amaris-production-web`, Render Standard, Frankfurt.
- PostgreSQL 17: `amaris-production-postgres`, Render Basic 1 GB, 5 GB disk.
- Celery broker: `amaris-production-broker`, Render Starter Key Value with journal/snapshot persistence and no eviction.
- Django cache: `amaris-production-cache`, Render Starter Key Value with LRU eviction and no persistence.
- Critical worker: payment fulfillment, invoice PDF archival and default critical jobs.
- Notification worker: transactional email/outbox jobs.
- Celery Beat: reconciliation and invoice-archive recovery schedules.
- Supabase Auth: project `epkcuseloinygkakxxdu`.
- Supabase Storage:
  - private student files: `Amaris Mathematics Academy`
  - private Django/CMS files: `amaris-cms-files`

## Release gates

The live frontend must not point to the production API until all of these pass:

1. Production Postgres, broker and cache are available.
2. Production Django build succeeds from the exact `production-20260922` SHA.
3. `python manage.py migrate --noinput` succeeds.
4. `python manage.py check --deploy` has no blocking errors.
5. `/health/` and `/health/ready/` return success.
6. Supabase JWT authentication accepts a synthetic verified student and rejects anonymous/invalid identities.
7. Cross-user student API isolation remains enforced.
8. Supabase Storage can write/read/delete a synthetic private object without exposing credentials.
9. PayFast remains server-verified; no real payment is generated during deployment tests.
10. A synthetic verified paid invoice can generate an idempotent PDF archive under `<student-uuid>/invoices/`.
11. Celery broker connectivity and worker startup are healthy.
12. Safe smoke tests pass for homepage, login, registration, courses, API health and static assets.
13. Rollback target is recorded before frontend cutover.

## Cutover

Only after all release gates pass:

1. Set the live frontend `CMS_API_URL` / public API configuration to `https://amaris-production-web.onrender.com/api/v1`.
2. Deploy the live frontend.
3. Run post-deploy browser smoke.
4. Run one synthetic authenticated student journey without a real payment.
5. Verify no increase in 4xx/5xx errors.
6. Keep the previous frontend/backend SHAs recorded for rollback.

## Rollback

If production health, authentication, authorization, payment status, or document access fails:

- restore the previous frontend API configuration;
- deploy the previous known-good frontend SHA;
- leave the production database intact;
- redeploy the previous known-good backend SHA;
- re-run health and synthetic authenticated smoke before reopening cutover.

## Capacity statement

Production readiness and verified concurrency remain separate.

- Production readiness: determined by the release gates above.
- Maximum verified concurrent users: only the last successfully completed production-like capacity test.
- 50,000 concurrent users verified: NO unless a controlled test has actually sustained at least 50,000 simultaneous users within the defined thresholds.
