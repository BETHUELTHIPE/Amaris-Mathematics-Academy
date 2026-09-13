# CI/CD quality gates and release controls

The `Quality Gates and Release` workflow validates every pull request to `main`, repeats the gates on `main`, publishes a multi-platform backend image to Docker Hub only after all gates pass, deploys that immutable image to staging, and allows production promotion only from a manual workflow run. It is a thin coordinator over reusable workflows so each gate has one owner.

## Workflow topology

| Workflow | Single responsibility |
|---|---|
| `quality-release.yml` | Triggers the pipeline, joins all blocking results and publishes the SHA-tagged release image |
| `ci.yml` | Python/Django and frontend correctness |
| `security.yml` | Dependency, secret, Compose, container, SBOM and vulnerability checks |
| `e2e.yml` | Browser route and WCAG smoke tests |
| `performance-smoke.yml` | Asset-size budgets and Lighthouse |
| `load-tests.yml` | Scheduled and operator-selected staging capacity profiles; retained instead of adding a duplicate `capacity.yml` |
| `deploy-staging.yml` | Reusable staging promotion and optional rollback drill |
| `deploy-production.yml` | Protected production acceptance, backup and promotion |

Post-deploy release verification is intentionally part of the deployment transaction rather than a separate `post-deploy.yml`. Both deployment workflows call `scripts/release/promote.sh`, which records version N, deploys N+1, verifies state and readiness, and restores and re-verifies N after failure. Splitting those steps would duplicate checks and weaken the rollback transaction.

## Blocking quality gates

| Gate | Enforcement |
|---|---|
| Python formatting | Black check |
| Python linting | Ruff check |
| Python static types | Mypy with Django settings loaded |
| Django correctness | System check, migration-drift check and a clean CI migration |
| Test suites | Unit, integration, permission, payment and full regression suites |
| Frontend correctness | ESLint, TypeScript, production build and Node tests |
| Accessibility | Pa11y against home, courses, contact, login and registration at WCAG 2 AA |
| Lighthouse | Performance 85%, accessibility 95%, best practices 90%, SEO 90%, plus Core Web Vitals lab budgets |
| Dependency security | `pip-audit` and `npm audit` with critical findings blocking |
| Secret security | Full-history Gitleaks scan |
| Container quality | Docker Compose validation and a clean production-image build |
| Container security | Trivy blocks critical image vulnerabilities |
| Supply-chain record | CycloneDX JSON SBOM plus BuildKit provenance/SBOM attestations |

The container, image publishing and deployment jobs use normal successful-job dependencies. They do not use `always()`, so a failed or cancelled critical gate prevents image publication and deployment. Report uploads may use `always()` because they do not release software.

## GitHub repository protection

Configure the following settings in the GitHub repository before enabling deployments:

1. Protect `main` and require a pull request.
2. Require every check emitted by the `CI`, `Security`, `E2E and accessibility`, and `Performance smoke` reusable workflow calls. Select the exact check names from a completed pull-request run so GitHub stores their current qualified names.
3. Require branches to be current before merging and dismiss approvals when new commits arrive.
4. Prevent force pushes and branch deletion.
5. Enable GitHub secret scanning and push protection when available.
6. Create a Docker Hub access token with read/write permission for the `bethuelm/amaris-mathematics-academy` repository.

## Docker Hub publishing

Create this GitHub Actions repository secret:

- `DOCKERHUB_TOKEN`: a Docker Hub personal access token with permission to push to `bethuelm/amaris-mathematics-academy`

The Docker Hub username is fixed to `bethuelm` in the workflow. Never store the Docker Hub password or access token in source code, repository variables, workflow logs or image layers.

After every successful push to `main`, the workflow publishes both of these Linux `amd64` and `arm64` tags:

- `bethuelm/amaris-mathematics-academy:<full-commit-sha>`
- `bethuelm/amaris-mathematics-academy:latest`

Staging and production use the immutable full-commit-SHA tag. The mutable `latest` tag is provided for convenient manual pulls only.

## Environments

Create two GitHub environments with these exact names:

### `staging`

Environment variables:

- `STAGING_URL`: user-facing staging URL
- `STAGING_HEALTHCHECK_URL`: HTTPS Django readiness endpoint ending in `/health/ready/`

Environment secrets:

- `STAGING_DEPLOY_WEBHOOK_URL`
- `STAGING_DEPLOY_TOKEN`

Staging deploys automatically after a successful push to `main`. Restrict its secrets to the staging environment; never reuse production credentials.

### `production`

Environment variables:

- `PRODUCTION_URL`: user-facing production URL
- `PRODUCTION_HEALTHCHECK_URL`: HTTPS Django readiness endpoint ending in `/health/ready/`

Protected environment secrets:

- `PRODUCTION_DEPLOY_WEBHOOK_URL`
- `PRODUCTION_DEPLOY_TOKEN`
- `PRODUCTION_BACKUP_WEBHOOK_URL`
- `PRODUCTION_BACKUP_TOKEN`

Configure at least one required reviewer, disable administrator bypass where policy permits, and restrict the deployment branch to `main`. GitHub stores the secrets; do not place their values in repository variables, workflow YAML, deployment responses or logs.

The workflow cannot create environment reviewers from source code. Production approval becomes enforceable only after the repository owner configures required reviewers in the GitHub environment settings.

## Release flow

1. A pull request must pass every quality and security gate.
2. Merging to `main` repeats the gates and publishes `docker.io/bethuelm/amaris-mathematics-academy:<commit-sha>` and `:latest`.
3. The workflow records the currently active immutable release (version N), deploys the SHA-tagged candidate (version N+1), and checks both deployment state and readiness.
4. If staging is unhealthy or reports the wrong Git SHA or Docker tag, the workflow rolls back to the exact version N image and verifies that version N is active and healthy.
5. To deploy production, run `Quality Gates and Release` manually, enable **Promote the tested release to production**, and select the migration risk.
6. GitHub pauses the production job for its required environment reviewer.
7. The production-acceptance manifest must show all 20 criteria as passed, evidenced, dated and reviewer-approved.
8. A high-risk migration requires a successful backup response containing a non-empty `recovery_id` before deployment starts.
9. Production readiness and release identity are verified after deployment. A failed check must restore the exact previous image, prove its Git SHA and Docker tag, pass readiness, and leave the workflow failed for investigation.
10. Each staging deployment stores a 90-day JSON release record; each production deployment stores a 365-day record containing the candidate, previous and restored immutable identities.

The authoritative evidence requirements and current pre-production status are in [`ACCEPTANCE_CRITERIA.md`](ACCEPTANCE_CRITERIA.md). A build or manual approval cannot bypass the acceptance verifier.

## Deployment webhook contract

The hosting platform must expose an authenticated HTTPS webhook supporting exactly three actions: `status`, `deploy` and `rollback`. It must reject arbitrary shell commands and unapproved image repositories.

A status request contains:

```json
{
  "action": "status",
  "environment": "production",
  "image": "",
  "release_sha": ""
}
```

It must return the release currently serving traffic:

```json
{
  "status": "ready",
  "active": {
    "image": "docker.io/bethuelm/amaris-mathematics-academy:<full-commit-sha>",
    "git_sha": "<full-commit-sha>"
  }
}
```

Deploy and rollback requests contain the exact target image and its matching Git SHA:

```json
{
  "action": "deploy",
  "environment": "production",
  "image": "docker.io/bethuelm/amaris-mathematics-academy:<full-commit-sha>",
  "release_sha": "<full-commit-sha>"
}
```

The adapter must return HTTP 2xx only after accepting the action. It must set `APP_RELEASE_GIT_SHA` and `APP_RELEASE_IMAGE_TAG` on the web container. The Django `/health/ready/` response publishes these two non-secret identifiers, allowing the workflow to prove which release is healthy.

For `deploy`, retain at least the previous two known-good immutable images and configurations. For `rollback`, atomically restore the exact `image` and `release_sha` in the request. A rollback is not considered successful merely because the webhook returned 2xx: the status response and readiness endpoint must both report version N before the workflow records recovery.

The backup webhook receives `action: backup` and `tag: pre-migration`. It must wait for a verified encrypted backup and return:

```json
{
  "status": "succeeded",
  "recovery_id": "opaque-recovery-point-reference"
}
```

A timeout, non-2xx result, failed status or missing recovery reference stops a high-risk production release.

## Staging rollback drill

Run the workflow manually with **rollback_test** enabled and **deploy_production** disabled. The job records version N, deploys N+1, deliberately enters the rollback path, restores N, and passes only when status and readiness both identify N. Use a new commit so N+1 differs from the staging release already active. A successful drill produces a `rollback_test_passed` deployment record; it never promotes the candidate to production.

## Recovery and operations

- Keep the previous two known-good images available for rapid rollback.
- Never reuse the mutable `latest` tag for a production decision; release by commit SHA.
- Database migrations must follow the expand/migrate/contract pattern described in the disaster-recovery runbook.
- When a schema is not backwards compatible, stop the release and use a reviewed maintenance procedure instead of relying on automatic rollback.
- Review Lighthouse reports for 14 days and SBOM artifacts for 30 days; retain production release and approval records according to the organisation's audit policy.

The broader database restoration, Redis/Celery recovery and RPO/RTO policy is in [`backend/docs/DISASTER_RECOVERY.md`](../backend/docs/DISASTER_RECOVERY.md).
