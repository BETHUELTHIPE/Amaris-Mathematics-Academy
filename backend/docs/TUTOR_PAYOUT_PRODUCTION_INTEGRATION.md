# Tutor earnings release — production branch integration

## Scope and identity

Integration branch `feature/production-tutor-finance-0013-20261015` is based on the *actual* Render production branch `production-release-20260923` at commit `4818aa8644edfedb012dca70559f1cf6d397a628`, not the divergent `main` branch. It retains the existing `VideoRequest` PayFast checkout and Supabase-authenticated tutor API. It does **not** introduce another video order, payment reference scheme, or staff login.

Django migration `content.0013_tutor_finance` depends on the applied `content.0012_tutor_recruitment`; it introduces five additive finance tables only: `TutorPaymentProfile`, `TutorContract`, `TutorCourseAssignment`, `TutorEarning`, and `TutorPayout`. PostgreSQL RLS and revocation of `anon` / `authenticated` Data API permissions protect all five. Do not migrate production until you have a verified restore.

## Server-owned accounting

- Signed, effective-dated tutor contracts determine the split (e.g. 60/40 or 50/50) as it stood at the time of the provider-verified payment. One tutor course assignment must be unambiguous. Sale references are unique per service so a duplicate ITN cannot double-pay.
- Course ledger entries are created after PayFast verification and enrollment. Live-class entries are created for confirmed paid bookings; completed class attendance is superuser-reviewed.
- Video earnings reuse the existing `VideoRequest` flow and are credited only after a verified successful payment **and** an assigned tutor. Unassigned paid requests remain unattributed until the existing Admin workflow assigns a tutor and the reconciliation task runs. A ready private video asset is required for eligibility.
- Financial data is superuser-only in Django Admin. Tutors authenticate using the existing verified Supabase tutor session at `GET /api/v1/tutor/earnings/`; this is an *additional* aggregate endpoint, not a replacement for live-class scheduling. It exposes service totals, unique paid-student counts, and a bank-account mask, not student identities.
- Bank numbers are encrypted with `TUTOR_BANK_FERNET_KEY` (Fernet key). Generate and store it in Render secret environment configuration; **never** commit it, paste it into issues, or rotate it without a re-encryption plan. Changes to bank numbers disable recipient verification.
- The finance reconciler can move an earned amount to `READY` after the settlement hold plus fulfillment; it creates `TutorPayout(state=awaiting_provider)` only. **There is no integrated bank transfer provider and no actual EFT.** No receipt is sent unless an independently verified provider transfer has a reference, settlement timestamp and `paid` state. The release must **not** be described as automatic bank payout.

## Database isolation and backup — release blockers

**Staging isolation:** Supabase contains the role `amaris_staging_app` and schema `amaris_staging`, but the last verified inventory showed no Django tables under that schema. Because the staging Render service automatically executes `python manage.py migrate`, do NOT push this branch to the `staging` deployment branch unless the effective Render staging database credentials and `search_path` have been verified as isolated. Run `SELECT current_user, current_schema(), current_setting('search_path')` from the **staging server**, then verify that table creation cannot reach production `public`. Do not expose the connection string in logs.

**Production backup:** The GitHub `Backup Restore Verification` CI job tests *throwaway* PostgreSQL containers. It is not an actual production Supabase backup. Before applying migration 0013, export a verified, encrypted pg_dump of the real Supabase database using the Database connection details in the private Dashboard. Prefer `pg_dump --format=custom --no-owner --no-privileges --file=amaris-production-<timestamp>.dump` with credentials read securely, not typed into a shell history. Restore it to a **separate database on a separate instance** using `pg_restore --exit-on-error --no-owner --no-privileges`. Record UTC timestamp, source database server ID, encrypted archive checksum, restore verification, and responsible approver. Never restore into the production or staging database during testing. The free plan may not include managed backups; manual secure export/restore is required.

## Release steps

1. Run `python manage.py makemigrations --check --dry-run`, `python manage.py migrate --plan`, OpenAPI --fail-on-warn, backend payment suite, browser E2E, security/secret scans and container checks on this branch; obtain green required checks.
2. Confirm staging isolation. Take and verify a backup of staging's isolated database. Deploy exact integration SHA to staging using the protected process; apply 0013 only in staging. Test server-verified mock/sandbox course/video/live-class purchases, replay, refunds, tutor privacy, and the finance Admin screens; never make real payments.
3. Capture a **fresh production Supabase backup and isolated restore evidence**, with explicit authorization for this additive migration. Ensure the account-encryption key exists before live bank details may be entered; disable scheduled ledger reconciliation if no Celery worker exists.
4. After full signoff, promote the exact tested SHA to the production branch through the protected workflow, let Django apply migration 0013, verify live health and read-only tutor earnings, monitor errors, and stop or rollback application code on critical failures. Schema migration is additive, not automatically rolled back.
5. Do not enable actual payouts without an audited disbursement provider, verified payee ownership, signed settlement callbacks, idempotency, refund/reversal reconciliation, disputes/tax handling and a successful test transfer.

**No production deployment or database migration is performed by this PR.**
