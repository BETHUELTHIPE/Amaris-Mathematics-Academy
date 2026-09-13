# Production approval and deployment

The existing `quality-release.yml` coordinator calls `deploy-production.yml` only
after main CI, security, image publication and staging checks succeed. Production
is a separate GitHub environment. Its single deployment job has the shared
`amaris-production` concurrency group with `cancel-in-progress: false`; future
production/rollback workflows must use this same group. GitHub concurrency can
replace a pending run and does not promise FIFO ordering. It does not interrupt
the running production transaction.

## Required repository setup

Repository: `BETHUELTHIPE/Amaris-Mathematics-Academy` (public when this change was
prepared). Native environment reviewers are supported for public repositories on
current GitHub plans. A YAML `environment: production` declaration does not set up
reviewers or secret isolation by itself.

In [Settings → Environments](https://github.com/BETHUELTHIPE/Amaris-Mathematics-Academy/settings/environments):

1. Create or edit `production`.
2. Enable **Required reviewers** and select the release owner, `BETHUELTHIPE`, or
   another designated reviewer with repository access. Enable **Prevent self-review**
   when a second reviewer is available; enabling it for a sole owner can block all releases.
3. Disable **Allow administrators to bypass configured protection rules**.
4. Choose **Selected branches and tags**. Add the **Branch** rule `main` only;
   remove wildcard rules and tag rules. Protect `main` with PR review and required CI.
5. Add the environment secrets/variables below. Remove repository- or
   organisation-level copies of production credentials and exclude this repository
   from organisation secrets that would expose production access to other jobs.
6. Review the deployment with its full Git SHA, registry digest, staging evidence,
   acceptance manifest and migration risk before selecting **Approve and deploy**.

The first production step reads the actual environment rules and this workflow
run's review history using the read-only `GITHUB_TOKEN`. Missing reviewers,
unapproved runs, unsupported APIs/plans, tag/wildcard policies, a wrong SHA, and
unreadable protection settings block the job. The code cannot silently downgrade
approval to a boolean input or an unprotected manual trigger. If native required
reviewers are unavailable after a plan/visibility change, keep deployment disabled
until an appropriate protected environment or separately reviewed external approval
system is available. Never move production credentials to repository scope as a workaround.

The current connector can edit workflow files but cannot configure GitHub environment
administration or enumerate/move secret values. These settings must be verified by
the repository owner. This PR does not assert that the environment is configured.

Sources: [GitHub environment protection and secret scope](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments),
[environment setup and plan support](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments),
[deployment concurrency](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments).

## Secret and variable scope

| Location | Names | Purpose |
| --- | --- | --- |
| Production environment secrets | `PRODUCTION_DEPLOY_WEBHOOK_URL`, `PRODUCTION_DEPLOY_TOKEN` | Hosting transaction API |
| Production environment secrets | `PRODUCTION_BACKUP_WEBHOOK_URL`, `PRODUCTION_BACKUP_TOKEN` | Verified recovery point |
| Production environment secrets | `PRODUCTION_STUDENT_EMAIL`, `PRODUCTION_STUDENT_PASSWORD` | Dedicated verified student fixture with access to the fixture lesson |
| Production environment variables | `PRODUCTION_URL`, `PRODUCTION_HEALTHCHECK_URL` | HTTPS origin and backend `/health/ready/` endpoint |
| Production environment variables | `PRODUCTION_COURSE_PATH`, `PRODUCTION_LESSON_PATH` | Real course and protected, pre-entitled lesson paths |
| Staging environment only | Existing `STAGING_*` and load-test secrets | Staging deployment and tests |
| Repository secret | `DOCKERHUB_TOKEN` | Image publication only; must not grant hosting or database access |

Production secrets are referenced only on the deployment transaction step in the
job attached to `production`. No reusable workflow call uses `secrets: inherit`.
CI, image building/publishing, staging and report uploads do not receive production
environment secrets. The browser child receives synthetic account credentials only,
with deploy/backup/GitHub tokens removed. Dependency preparation runs before that step.
Database, application and backup-storage credentials stay at the hosting platform.
Environment scope is not protection against a repository administrator changing
workflow code: required reviews and branch protection are also necessary.

## After approval

1. Verify native approval, exact main SHA and the existing acceptance evidence.
2. Hash the Docker registry manifest again and compare it to the digest recorded by
   image publication. Enforce the full SHA tag and approved repository; reject `latest`.
3. Prepare the existing locked browser dependencies before changing production.
4. Ask the adapter to verify registry identity, readiness, compatibility and watchdog
   support. Acquire an exclusive hosting lease and capture the actual healthy version N.
5. Create a new verified backup for **every** production release, including low-risk
   and repeated releases. Require a recovery ID tied to this transaction and candidate.
6. Inspect candidate migrations. Reject destructive/backwards-incompatible changes.
7. Deploy `repository:full-git-sha@sha256:digest`; run the safe migration command once
   under a PostgreSQL advisory lock, with lock and statement timeouts.
8. Verify hosting state and readiness, including the full SHA, tag and active digest.
9. Check public pages, deny anonymous dashboard/lesson access, sign in as the verified
   fixture student, verify server auth state, visit the dashboard/course/entitled lesson.
10. Sample identity, health and production telemetry ten times over five minutes.
    Any critical alert, failed check, timeout or unknown response fails the release.
11. Commit only after all checks pass. Commit disarms the watchdog and releases the lease.

Every failure after the deployment request is issued, including an HTTP error whose
side effects are unknown, migration failure, browser failure, monitor failure or
runner cancellation, attempts rollback to the **captured** previous digest. Recovery
must prove version N's identity, health and student journey. The workflow remains
failed after recovery so a rolled-back release cannot appear successful. Failed
recovery emits a critical error and leaves the hosting watchdog/lease active.
No reverse database migration or automatic database restore is performed; expansions
must remain compatible with version N. A destructive migration requires its own
approved maintenance/restore plan.

## Hosting adapter API v2

This repository contains the client and migration command; it does not contain the
hosting webhook service. Its existing three-action v1 webhook is sufficient for
staging only. Production remains blocked until the adapter implements and is tested
against this v2 contract. Do not return fabricated success flags.

Every request uses authenticated HTTPS with no redirects and contains:

```json
{
  "contract_version": 2,
  "action": "preflight",
  "environment": "production",
  "transaction_id": "<github-run-id>-<attempt>",
  "image": "docker.io/bethuelm/amaris-mathematics-academy:<40-character-sha>",
  "git_sha": "<40-character-sha>",
  "digest": "sha256:<64-character-manifest-digest>",
  "image_reference": "docker.io/bethuelm/amaris-mathematics-academy:<40-character-sha>@sha256:<64-character-manifest-digest>"
}
```

Use `Idempotency-Key: <transaction_id>:<action>`. `status` and `monitor` must always
return fresh observations despite that header. Mutation requests must reconcile
duplicates. Other than `status`, a successful response must include
`status: "completed"`, the matching `transaction_id`, and, for requests naming a
release, `release: {image, git_sha, digest}` exactly matching that requested release.
An HTTP 202, `accepted`, missing fields or timeout is not completed evidence.

| Action | Required behavior and extra response fields |
| --- | --- |
| `preflight` | Verify the tag and digest against the registry; validate revision metadata and candidate config; prove hosting/DB/queue readiness and rollback support. Return `registry_verified`, `ready`, `rollback_compatible`, `watchdog_ready`, all `true`. |
| `acquire` | Atomically acquire the production lease, reject competing transactions, capture healthy previous `{image, git_sha, digest}` and arm a durable 1,200-second watchdog. Return `previous`, `watchdog_armed: true`. No code change yet. |
| `status` | Return `active: {image, git_sha, digest}` based on the running deployment, including the canonical multi-platform registry digest rather than a container config ID. |
| `backup` | Separate backup endpoint; create and verify a fresh recovery point for this transaction, candidate and production database. Return `verified: true` and non-empty opaque `recovery_id`. Retain server-side timestamp/checksum/restore evidence. |
| `migration-plan` | Run `python /app/ops/safe_migrate.py --plan` from the candidate digest against production; return `backwards_compatible: true`, `destructive: false` only if it succeeds. |
| `deploy` | Validate lease ownership and unchanged `previous`; pull the digest reference; retain previous configuration and image. Set release SHA/tag and `DEPLOYMENT_ENVIRONMENT=production`. Do not commit the transaction. |
| `migrate` | Validate the recovery ID server-side; run the candidate's `python /app/ops/safe_migrate.py` once, setting `RECOVERY_ID`, `APP_RELEASE_GIT_SHA`, `RELEASE_DIGEST`. Return `pending: 0`, `backwards_compatible: true` only on success. |
| `monitor` | Query current application errors, latency, database/queue health and critical alerts using production thresholds. Return `healthy: true`, `critical_alerts: 0` only when data is fresh and thresholds pass. Missing/stale telemetry fails. |
| `commit` | Verify current candidate, atomically mark the transaction successful, retain N for future recovery, disarm watchdog, release lease. |
| `rollback` | Cancel/reconcile candidate operations before restoring captured N and configuration. Must work after lost deploy/commit responses and remain idempotent. Reject any rollback target different from the lease's captured previous release. |
| `abort` | After a pre-mutation block or independently verified rollback, release the lease and disarm the watchdog; reject if an unverified candidate remains live. |

The durable watchdog must restore and verify N if the runner disappears, times out,
is force-cancelled, or never commits. It must serialize recovery with in-flight
deployment/migration requests, retain a server-side transaction audit and alert the
operator on failed recovery. GitHub process signal handlers alone cannot guarantee
recovery after runner loss. The watchdog also releases unused leases after a
pre-mutation runner failure. HTTP actions must finish within the client's 120-second
budget or expose a separately implemented bounded polling contract before use.

## Student journey and current blockers

Use a dedicated synthetic account with confirmed email and an existing fixture
entitlement. No real registration, payment, student record or purchase is created.
PayFast domains are blocked in the browser check. Authenticated lesson content must
render `[data-testid="lesson-content"]` with visible learning content, and anonymous
lesson access must redirect to login. Do not point the fixture at a public course page.

The inspected branch contains login, a verified dashboard and course pages, but no
complete protected lesson/checkout implementation. The mandatory fixture check will
block releases until that journey actually exists. End-to-end payment, enrollment,
progress persistence and real email delivery still require the existing acceptance
evidence; this browser smoke test does not certify them. This workflow publishes a
backend image; it does not deploy the separately hosted Sites frontend.

Local deterministic tests cover approval rejection, wrong image identity, preflight
and backup failures, unsafe migrations, lost deploy responses, migration/health/
student/monitor failures, cancellation, rollback failure, and repeated releases.
They do not prove a live hosting adapter, production backup or real student journey.
Complete a staging drill of API v2 and forced failure/recovery before accepting the
production release. The existing v1 staging rollback drill remains available.

Approval and deployment JSON records are retained as GitHub artifacts for 90 days
(the public-repository limit). Export them to controlled long-term audit storage if
the required retention period is longer. Review the record after every deployment.
