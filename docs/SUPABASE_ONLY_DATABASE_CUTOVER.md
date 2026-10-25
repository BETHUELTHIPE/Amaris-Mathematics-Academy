# Amaris: Supabase is the only application database

## Authority and architecture

Supabase project: `epkcuseloinygkakxxdu`, PostgreSQL 17.
Django CMS/DRF, Celery workers, payment, invoices, bookings and course state **must** read and write the same Supabase PostgreSQL project.
Student registration/authentication and its trigger-managed `public.student_profiles` stay in Supabase Auth/Postgres.
Frontend contact submissions call the Django API, and must report failure if it is unavailable. Cloudflare D1 is not an accepted fallback.
Redis is permitted **only** as transient cache, Celery broker and task-result infrastructure; it is not an authoritative relational database.
Supabase Storage keeps the two existing private file buckets. These are object storage, not additional relational databases.

## Pre-cutover gates — do not skip

1. Take and verify a restorable snapshot of the existing **Render production PostgreSQL** database and an independent Supabase backup. Preserve the original Render DB for rollback.
2. Perform a read-only comparison of both databases: Django migration names, data-model schema and row counts for students, accounts, enrollments, courses, invoices, bookings, payments, enquiries and verification events. Do **not** overwrite records or run a `pg_restore --clean` against live Supabase.
3. Resolve and document any divergent data. A populated Supabase schema alone does not prove that all records in Render PostgreSQL have been migrated.
4. Rotate the Supabase database password if it has ever been pasted into a chat, issue or public log. In the Supabase dashboard choose **Connect → Session pooler (5432)** for the persistent Render Django web/worker processes where direct IPv6 is unavailable. Copy the precise hostname. URL-encode special password characters.
5. On staging **and then** protected production Render services, set `DATABASE_URL` in the **secret manager only**; set `SUPABASE_ONLY_DATABASE=true`, `DATABASE_SSL_REQUIRED=true`, and `SUPABASE_PROJECT_REF=epkcuseloinygkakxxdu`. The guard refuses wrong hosts, SQLite, Render Postgres, non-SSL connections and transaction pooling on 6543. The Render Blueprint shares the web service's secret with all Celery workers.
6. Set `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` for frontend Auth. Set the **server-side** `CMS_API_URL` to the HTTPS Django endpoint ending in `/api/v1`. Never expose `DATABASE_URL` or a Supabase service role key in client bundles.
7. Run `manage.py showmigrations --plan` and non-destructive migration preflight against staging Supabase first. Any schema/data migration requires the existing destructive-operation gate, recovery point and explicit approval. Do not run production migrations until the backup, compatibility, permissions and rollback gates pass.
8. Run staging journeys for registration/OTP/login, contact enquiry and AI reply, payments (sandbox), bookings, invoicing, authorization isolation, uploads and access to private files. Ensure all persisted changes appear in **Supabase**, with no D1 writes and no Render Postgres writes.
9. Promote the exact tested immutable Git-SHA image, verify production health, PostgreSQL dependency health, data counts, Celery queues and error rates, and retain the previous image + data recovery plan. Do not delete the Render database merely because the app now points to Supabase.

## Known operational blocker

Render lists an independent production PostgreSQL database `amaris-production-postgres`, but its database has no public IP allowlist entries; the read-only connector cannot compare its records. The real production service's secret `DATABASE_URL` is not exposed by the Render connector. **Do not assume production is already using Supabase or that migration is complete.**

The legacy Render Postgres resource is intentionally retained in `render.yaml` so a future Blueprint sync cannot automatically destroy data. Decommission separately **after** verified backup, reconciled records and production acceptance.

## No secrets in source or logs

Never store a password or DSN in GitHub commits, GitHub Actions logs, issue comments, chat messages, screenshots or `NEXT_PUBLIC_*` variables. Logs may show only a redacted host/project reference and success/failure status.
