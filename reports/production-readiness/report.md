# Production readiness — paid video requests

Test date: 2026-10-08 (Africa/Johannesburg).

Code Git SHA: `d8dd87500dd76ad0e77a1a638252775213653fbc`.
Base: staging `06cce285590ed23df7efd4d24993e0c07a2ec614`.
Environment: local Python 3.12.14 / Node 24.19.0; isolated SQLite test database,
synthetic students/files and mocked gateway/email/storage where specified.
CI validates Python 3.13.15, PostgreSQL 17 and Redis separately.
Docker image: not built or deployed in this check. Render currently uses Git/Python and Node services.

## Executed checks

| Area | Result | Evidence and limits |
| --- | --- | --- |
| UNIT TESTS | PASS | 131 Django tests run, 128 passed and 3 skipped; 51 frontend tests passed. |
| INTEGRATION | PASS locally | Full Django regression suite, including payment, notifications, storage and student journeys; live integrations remain unverified. |
| AUTHENTICATION | PASS locally | Existing regressions, verified-student route guards and session-refresh routing; fresh live auth/email acceptance is pending. |
| AUTHORIZATION | PASS locally | Owner-only request status, document metadata and protected video/invoice routes; no live cross-account acceptance claim. |
| API | PASS | Strict OpenAPI generation/validation with no warnings. |
| DATABASE | FAIL acceptance | Migration drift check passes; local tests apply migration 0011. PostgreSQL RLS/concurrency and deployed migration acceptance are pending CI/staging. |
| PAYMENTS | FAIL acceptance | Server-owned prices and verified-callback regressions pass; no deployed PayFast sandbox-to-worker-to-inbox journey was completed. |
| E2E | FAIL acceptance | Frontend contract/render tests and local Render runtime smoke pass: homepage 200; four protected video routes redirect to login; unauthenticated checkout 401/private-no-store. Current-head responsive-browser and live authenticated video workflow acceptance are pending. |
| SECURITY | PASS locally | Black, Ruff, mypy; owner checks, unpaid fulfilment validation, private cache headers, payment replay/tamper regressions and cleanup regressions. External scans remain pending. |
| DEPENDENCY SCAN | FAIL acceptance | Fresh candidate CI scan pending. |
| SECRET SCAN | FAIL acceptance | Fresh candidate CI scan pending. |
| DJANGO DEPLOYMENT CHECK | PASS | `check --deploy --fail-level ERROR`, production settings enabled. |
| NEXT.JS/VINEXT BUILD | PASS | Shared Vinext production build and Render Node/Nitro production build completed. |
| PERFORMANCE | PASS assets only | Largest client chunk 214.1 KiB / 250 KiB; hero 57.0 KiB / 200 KiB. No traffic/load or Lighthouse acceptance claim. |
| BACKUP RESTORE | FAIL acceptance | Fresh candidate CI restore check and current production restore point are pending. |
| RECOVERY | FAIL acceptance | Local regression coverage passes; deployed worker/storage/SMTP outage recovery not demonstrated. |
| ROLLBACK | FAIL acceptance | Existing release/architecture contracts pass; no new production rollback drill performed. |

Also passed: 19 load/capacity-harness contract tests (no traffic), 11 release/architecture
contract tests and frontend TypeScript checking. ESLint passes with two existing warnings.
The local Black API check uses the Python 3.12 parser; CI runs the repository's Python 3.13 check.

## Fixes established by this verification

- Register supporting-document metadata as read-only in Django Admin.
- Type server-owned package prices correctly for mypy.
- Lock and recheck unpaid status before deleting expired uploads. Preserve metadata
  and retry when storage deletion fails; regression tests cover both paths.
- Permit only the specified PayFast submission and YouTube privacy-enhanced embed hosts
  in edge CSP; keep video-request responses private and rate-limit checkout.
- Refresh Supabase sessions on booking and video-request pages/API routes.
- Return HTTP 401 for unauthenticated video checkout and 403 for unverified students,
  rather than catching a login redirect and misreporting it as invalid form data.
- Replace deployment-adapter error suppressions with ambient types so type checking
  works both before and after Render adapters are installed; ignore generated Nitro output.
- Run existing quality/payment/restore gates on staging PRs and verify the Render runtime.

## Blocking failures

| Severity | Component | Evidence / required fix |
| --- | --- | --- |
| Critical | Workers/scheduler | Render service inventory on 2026-10-08 has no production critical worker, notification worker or beat service. Paid production resources remain paused by user instruction. Resume/provisioning is outside the current permitted work. |
| High | Release alignment | Backend still uses `production-release-20260923`; live frontend uses `render-live-current-20260918`. This candidate has not been promoted or deployed. |
| High | Storage/payment/email acceptance | On isolated staging, verify private upload, real PayFast sandbox ITN, queue entry, archived invoice, actual inbox notifications and ready-video playback with two synthetic students. Do not make real payments. |
| High | Database/recovery | Verify migration 0011 and private-table RLS on PostgreSQL; establish current backup/restore and rollback evidence before production promotion. |
| High | Release gates | Require fresh candidate CI security, browser, accessibility, Lighthouse, dependency and secret scan results. |

Publication/deployment authorization: the user explicitly approved publishing these
changes to the existing public GitHub repository and deploying on 2026-10-08.
The earlier automatic approval rejection is resolved by that explicit instruction.
Current-candidate CI and staging acceptance must pass before production promotion.
The existing pause on newly provisioned paid production resources remains in effect.
This report records the local validation baseline; CI and deployment evidence must
be recorded separately as those actions complete.

PRODUCTION READINESS: FAIL

MAXIMUM VERIFIED CONCURRENT USERS: 0 in this verification (no load test run).

50,000 CONCURRENT USERS VERIFIED: NO

FINAL RESULT: **NOT READY FOR PRODUCTION**
