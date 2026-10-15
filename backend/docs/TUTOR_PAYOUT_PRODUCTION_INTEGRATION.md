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

**Staging isolation:** Read-only Supabase role inspection on 15 October 2026 verified that `amaris_staging_app` has `search_path=amaris_staging, public`, can CREATE objects in `amaris_staging`, cannot CREATE objects in `public`, and has no SELECT or write privilege on any of the 40 production `public` tables inspected. The `amaris_staging` schema itself still has **zero tables**. These facts do NOT establish which credentials Render staging is using.

The quality-release workflow now invokes `scripts/release/verify_staging_database_isolation.py` **before** moving the staging Git branch. It uses only the `staging` GitHub protected environment secret `STAGING_DATABASE_URL`, never the production connection variable. It fails closed unless the actual connected role, schema, first `search_path` schema, and public permissions are safe. **This verifies the GitHub secret's connection, not the Render service's environment**: the operator must separately verify Render staging's effective `DATABASE_URL` refers to the same restricted role/schema and the same database server. Stage-specific environment groups and secret-file overrides must also be checked. Do not proceed merely because this workflow step passes.

**Production backup:** The CI `Backup Restore Verification` workflow tests disposable PostgreSQL containers; it is not a production database backup. A genuine encrypted **export and isolated restore test** are required. Supabase's [official CLI backup/restore guide](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore) uses **three logical files**: `roles.sql`, `schema.sql`, and `data.sql`. Supabase-specific filters are provided by the CLI. A normal raw `pg_dump` of every managed internal schema is not an equivalent substitute. The database dump does not back up the actual objects in Supabase Storage buckets—back up those object bytes independently.

### Genuine production backup runbook (operator, private workstation)

1. Install current Supabase CLI, Docker, PostgreSQL `psql`, `age`, `tar`, `sha256sum`, and Python 3; consult `supabase db dump --help`. Use a trusted, encrypted local drive. Select an output directory **outside** the Git repository.
2. Get the production **session-pooler** connection string in [Supabase Connect](https://supabase.com/dashboard/project/epkcuseloinygkakxxdu), then retrieve the database password privately. Rotate exposed/old credentials first. Never paste connection strings, passwords, decrypted backups or private encryption keys in this chat, GitHub issues or logs.
3. Export required variables in the operator's private shell or secret manager (values intentionally omitted):
   ```bash
   export SUPABASE_PRODUCTION_DATABASE_URL="<from-private-secret-manager>"
   export AMARIS_BACKUP_AGE_RECIPIENT="<age-public-recipient>"
   export AMARIS_BACKUP_OUTPUT_DIR="<absolute-secure-directory-outside-repository>"
   bash scripts/release/export_production_supabase_backup.sh
   ```
   The script validates the **production project reference**, emits a dated **age-encrypted archive and SHA-256 manifest**, and never stores SQL in Git. Archive creation alone is not a successful restore test.
4. Use an entirely separate, explicitly identified Supabase project for recovery testing. Follow the [Supabase official restore procedure](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore), including special considerations for database roles, custom `auth`/`storage` modifications, encryption keys, and extensions. Decrypt only on an encrypted private workstation, verify the encrypted archive's SHA-256, and restore **there**, never to the existing live or staging project.
5. After the restore, run `scripts/release/verify_production_supabase_restore.sh` using `AMARIS_RESTORE_DATABASE_URL` and `AMARIS_RESTORE_PROJECT_REF` set to the separate project. This read-only script rejects the production project reference, checks the restored core Django/Auth tables and `0012` migration, and reports aggregate counts. Compare those counts to read-only source counts. Perform a separate application recovery smoke test on the isolated target before declaring the backup proven.
6. Record timestamp (UTC), production and **distinct** restore project refs, encrypted archive SHA-256, source-versus-restored table counts, restore/app-smoke-test outcome, storage object backup status, and approval in a **private** release record. Do not share student or bank data.

Neither the Supabase integration nor the Render integration currently provides a supported `pg_dump`, secure file-export or remote-shell operation here. Therefore a genuine production export and restore **cannot be claimed complete until an operator runs these steps and provides non-sensitive evidence**. Supabase Free does not include managed daily project backups; an encrypted CLI export is the supported manual path.


## Release steps

1. Run `python manage.py makemigrations --check --dry-run`, `python manage.py migrate --plan`, OpenAPI --fail-on-warn, backend payment suite, browser E2E, security/secret scans and container checks on this branch; obtain green required checks.
2. Confirm staging isolation. Take and verify a backup of staging's isolated database. Deploy exact integration SHA to staging using the protected process; apply 0013 only in staging. Test server-verified mock/sandbox course/video/live-class purchases, replay, refunds, tutor privacy, and the finance Admin screens; never make real payments.
3. Capture a **fresh production Supabase backup and isolated restore evidence**, with explicit authorization for this additive migration. Ensure the account-encryption key exists before live bank details may be entered; disable scheduled ledger reconciliation if no Celery worker exists.
4. After full signoff, promote the exact tested SHA to the production branch through the protected workflow, let Django apply migration 0013, verify live health and read-only tutor earnings, monitor errors, and stop or rollback application code on critical failures. Schema migration is additive, not automatically rolled back.
5. Do not enable actual payouts without an audited disbursement provider, verified payee ownership, signed settlement callbacks, idempotency, refund/reversal reconciliation, disputes/tax handling and a successful test transfer.

**No production deployment or database migration is performed by this PR.**
