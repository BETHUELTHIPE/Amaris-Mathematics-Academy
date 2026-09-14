# Production Readiness Report

## Release identity

- **Git SHA:** `1bd4116968ed6bac1f5f49f19514cceedbf152b1` (tested PR head)
- **CI merge SHA:** `5fccfc77421b8962cc38a86448f43f4518118739` (GitHub Actions pull-request merge ref used for image build and scans)
- **Docker image:** CI built and scanned `amaris-backend:5fccfc77421b8962cc38a86448f43f4518118739` and `amaris-nginx:5fccfc77421b8962cc38a86448f43f4518118739`. The immutable registry target is `docker.io/bethuelm/amaris-mathematics-academy`, but the publish job was intentionally skipped for this pull-request run, so no release image was published from this evidence set.
- **Test date:** 2026-09-13
- **Environment:** GitHub Actions pull-request CI for `security/owasp-test-suite`; Ubuntu 24.04 runner, PostgreSQL 17 and Redis 8 CI services; staging and production deployment jobs were not executed.

> **Status semantics:** `PASS` means the automated evidence required for that category passed on the tested release candidate. `FAIL` means required production-like or staging evidence is incomplete or was not executed. Passing unit/contract checks does not substitute for a required deployment, recovery, restore, provider, or capacity drill.

## Production readiness vs capacity

**PRODUCTION READINESS:** **FAIL**

**MAXIMUM VERIFIED CONCURRENT USERS:** **NOT ESTABLISHED**

**50,000 CONCURRENT USERS VERIFIED:** **NO**

**CAPACITY TEST ENVIRONMENT:** **NOT EXECUTED**

**TEST TOOL:** **NOT EXECUTED**

**TEST DURATION:** **NOT EXECUTED**

**PEAK VERIFIED REQUEST RATE:** **NOT AVAILABLE**

**P95 RESPONSE TIME:** **NOT AVAILABLE**

**P99 RESPONSE TIME:** **NOT AVAILABLE**

**ERROR RATE:** **NOT AVAILABLE**

**CAPACITY EVIDENCE:** **NONE — no completed controlled capacity/load test report exists for this release candidate**

No completed controlled capacity test has established a maximum concurrent-user count for this release candidate. Therefore the report deliberately uses `NOT ESTABLISHED` rather than inventing a numeric capacity result. Production readiness and capacity certification are separate conclusions. A future release may be production-ready without being verified for 50,000 concurrent users, but no positive concurrency claim may be made until an actual controlled test demonstrates it.

A concurrency level only counts as verified when the applicable workload acceptance criteria pass together: HTTP/API error rate, response-time thresholds, database stability, Redis/cache stability, application-worker stability, CPU/memory utilisation, connection-pool health, queue backlog, crash/restart behavior, and critical student journeys. Payment-provider endpoints must remain excluded from unsafe load generation. If a higher stage fails, the report must retain the highest lower stage that actually passed all required criteria.

## Readiness matrix

| Area | Result | Evidence / note |
|---|---|---|
| UNIT TESTS | **PASS** | Django unit tests and the complete Django regression suite passed in Quality Gates and Release #186. |
| INTEGRATION | **PASS** | Real integration tests and integration tests passed in Quality Gates and Release #186. |
| AUTHENTICATION | **PASS** | Frontend unit/authentication lifecycle tests passed. Provider-level delivery and production-domain verification remain part of the staging release gate. |
| AUTHORIZATION | **PASS** | Authorization and RBAC tests passed, including the Super Administrator user-management coverage in the regression suite. |
| API | **PASS** | DRF API tests passed, including validation, method handling, filtering, pagination, throttling, malformed-request and error-path coverage implemented by the suite. |
| DATABASE | **PASS** | Migration drift check, CI migrations and database-backed integration/regression tests passed against PostgreSQL 17. |
| PAYMENTS | **FAIL** | Automated payment tests passed, but approved payment-provider sandbox/staging evidence has not been executed and retained for this release candidate. |
| E2E | **FAIL** | The protected staging deployment/E2E job was skipped on the pull-request run; deployed frontend/API/authenticated journeys were not executed against a published immutable image. |
| SECURITY | **PASS** | Security Test Suite #150 passed. Backend and Nginx container scans also passed with fail-closed HIGH/CRITICAL gates. Production-like TLS/header/observability verification is still pending staging. |
| DEPENDENCY SCAN | **PASS** | Python and production Node dependency vulnerability gates passed. |
| SECRET SCAN | **PASS** | Repository secret scanning and the dedicated security workflow passed. |
| DJANGO DEPLOYMENT CHECK | **PASS** | Django deployment/security checks passed in the dedicated security pipeline. |
| NEXT.JS BUILD | **PASS** | Production build, lint, TypeScript, frontend unit/auth tests, accessibility, Lighthouse and frontend performance budgets passed. Next.js Production Check #29 also passed. |
| PERFORMANCE | **FAIL** | Lighthouse and frontend performance budgets passed, and the load-test safety contract passed, but no controlled staging capacity/load test was executed. No positive concurrent-user capacity claim is supported. |
| BACKUP RESTORE | **FAIL** | No successful production-like backup-and-restore drill is recorded for this release candidate. |
| RECOVERY | **FAIL** | No end-to-end service/disaster recovery drill has been executed and verified for this release candidate. |
| ROLLBACK | **FAIL** | Rollback capability and contracts exist, but no deployed staging drill proving version N -> N+1 -> health failure -> N restored has been completed for this release candidate. |

## GitHub Actions evidence

All four pull-request workflows passed for the tested PR head:

- **Quality Gates and Release #186** — PASS
- **Security Test Suite #150** — PASS
- **Docker and Nginx Validation #77** — PASS
- **Next.js Production Check #29** — PASS

Within Quality Gates and Release #186, the following completed successfully: repository secret scan; frontend lint, TypeScript, production build, unit/authentication tests, accessibility and Lighthouse; Python formatting, linting and typing; Django system/deployment checks, migration drift and migrations; unit, integration, API, RBAC, payment and full regression tests; dependency vulnerability gates; Docker/Compose validation; SBOM generation; and fail-closed HIGH/CRITICAL backend and Nginx container scans.

The following release jobs were intentionally skipped on this pull-request run and therefore do **not** count as production evidence:

- Publish release image to Docker Hub
- Staging deploy, migrate, verify, and approve release candidate
- Production approval, deploy, and verify production

## FINAL RESULT

# **NOT READY FOR PRODUCTION**

The codebase has a green automated CI/security baseline, but the release is not production-ready until the mandatory production-like operational gates below are completed successfully with retained evidence.

## Blocking failures

| Blocking failure | Severity | Affected component | Recommended fix |
|---|---|---|---|
| Staging deployment and E2E verification not executed | **CRITICAL** | Release pipeline / frontend / API / authentication | Publish the exact immutable candidate image, deploy it to the protected staging environment, run migrations safely, then execute health, static-asset, API and authenticated E2E journeys against that deployed version. |
| Backup restore proof missing | **CRITICAL** | PostgreSQL / disaster recovery | Take a release backup, restore it into an isolated production-like staging database, verify integrity, migrations and application smoke tests, and retain the restore evidence. |
| Rollback drill not completed | **CRITICAL** | Deployment / recovery | In staging, establish version N, deploy N+1, trigger a safe health-check failure, roll back to N, and prove health/readiness plus data compatibility after restoration. |
| Production environment approval not executed | **CRITICAL** | Deployment governance | Use the protected production GitHub environment and require explicit authorized production approval only after every mandatory staging gate is green. |
| Payment-provider staging evidence missing | **HIGH** | Payments / PayFast | Run the approved sandbox/staging payment flow end to end: checkout creation, redirect/return, signed webhook/IPN validation, idempotency, reconciliation, duplicate handling and failure paths. Do not make a real production payment for the test. |
| Controlled capacity/load test not executed | **HIGH** | Django / Next.js / PostgreSQL / Redis / Nginx | Run the controlled production-like staging load plan using synthetic users and record throughput, p95/p99 latency, error rate, CPU/memory, database connections/locks, Redis health and queue behavior. Do not claim 50,000 concurrent users unless that level is actually demonstrated. |
| Service/disaster recovery drill not executed | **HIGH** | Operations / observability / data | Simulate a controlled service or dependency failure in staging, execute the recovery runbook, and verify application health plus measured RTO/RPO after recovery. |
| Production-like TLS/header/observability verification pending | **HIGH** | Edge / Nginx / Cloudflare / monitoring | Verify the deployed staging URL for TLS, security headers, protected-route cache behavior, health/readiness, logs, metrics and alert delivery before production promotion. |
| Email delivery and DNS evidence pending | **HIGH** | Authentication / notifications | Verify production-domain SPF, DKIM and DMARC, then validate OTP/password-reset delivery, expiry, replay resistance, invalid-code behavior and failure handling with dedicated synthetic accounts. |
| Manual device/accessibility acceptance pending | **MEDIUM** | Frontend UX / accessibility | Complete keyboard, screen-reader and representative mobile/desktop browser checks and retain acceptance sign-off before promotion. |

## Release decision

Do **not** merge or deploy this candidate to live production solely because pull-request CI is green. Promote only after the immutable release image has passed protected staging, provider integration checks, backup/restore, rollback/recovery, controlled capacity testing and the explicit production approval gate.

> This report records the last fully verified release-candidate evidence set. Updating this documentation or its reporting contract creates a later commit; that later commit must not be treated as tested until its own required workflows complete successfully.
