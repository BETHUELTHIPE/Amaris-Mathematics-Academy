# Staging-only marketing media verification — PR #207

Production and `main` are out of scope. This file belongs to the `staging` branch to ensure a normal GitHub content commit prompts Render's staging auto-deploy webhook.

## Expected candidate and isolation
- Candidate feature commit: `001ba9524ac008ea9ebcb609c9c94e2f7de159e0` (PR #207).
- Render staging backend: `srv-dam2iivcgkoc7383tq50` (branch `staging`).
- Render staging frontend: `srv-daqf69qd0e5s73ac62n0` (branch `staging`).
- Do not merge into `main`, update `production-release-20260923`, or trigger production services.
- Staging Django must use an **isolated** PostgreSQL identity/database and the expected S3 CMS bucket configuration before testing.
- Confirm `STORAGES["default"]["BACKEND"]` is `storages.backends.s3.S3Storage`, `CMS_STORAGE_BUCKET_NAME=amaris-cms-files`, both Supabase buckets are configured, and S3 credentials are set only as Render secrets. Fail closed if storage silently falls back to filesystem.

## Verify these steps with genuine staging evidence
1. Check deployed backend and frontend SHA through Render deployment records and `/health/version/`, including successful Django `content.0008_announcement_media` migration on isolated staging database.
2. Using a staging-only Django superuser, create an **unpublished** disposable announcement and upload one safe JPEG/PNG, MP4/WebM, and PDF, each with unique marker names under `marketing/announcements/`. Do not include personal information or use real student data.
3. Confirm all three objects exist in Supabase S3 `amaris-cms-files` and not in student storage. Verify upload size, format checks, correct MIME handling, and that files >50 MiB are rejected.
4. While unpublished, ensure the public announcement and every asset download endpoint return 404. Publish, confirm media URLs redirect with short-lived signed URLs, and actually GET each file to compare bytes/hash. Confirm browser image rendering, video playback and PDF retrieval. Then expire/unpublish, and recheck access denial. Already-issued signed URLs remain valid until expiry.
5. Confirm ordinary staff, tutors and anonymous visitors cannot GET/POST/PUT/DELETE Django marketing Admin; ensure no unauthorised database or storage mutations. Verify a superuser can add, edit, publish, unpublish, and delete marketing records.
6. Delete disposable marketing announcement records and verify database cleanup. S3 objects need separate audited cleanup; Django record deletion alone is not proof of S3 object removal. Record SHA, UTC timestamps, HTTP statuses, artifact hashes, and test output.
7. Require a genuine production PostgreSQL encrypted backup and a successful isolated restore **before any production release**. The repository backup GitHub workflow uses synthetic data and does not meet this requirement. Reconcile marketing migration to the production branch, which already contains migrations through `0013`.

If credentials, staging isolation, or file verification are missing, report `NOT VERIFIED` instead of claiming success.
