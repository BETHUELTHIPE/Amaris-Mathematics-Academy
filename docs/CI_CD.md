# CI/CD quality gates and release controls

The `Quality Gates and Release` workflow validates every pull request to `main`, repeats the gates on `main`, publishes a multi-platform backend image to Docker Hub only after all gates pass, deploys that immutable image to staging, and reaches the protected production approval gate after a successful main release (or an explicitly requested manual main run). It is a thin coordinator over reusable workflows so each gate has one owner.

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

`post-deploy.yml` verifies staging identity after its test gates. Staging uses `scripts/release/promote.sh`. Production uses the stricter `scripts/release/production_deploy.py` transaction for digest verification, backups, safe migrations, student checks, five-minute monitoring and verified rollback. See [Production deployment](PRODUCTION_DEPLOYMENT.md) for required environment setup and the hosting adapter API v2 contract.

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

Staging uses the full-commit-SHA tag. Production also requires the publication digest and deploys the combined SHA tag plus digest reference. The mutable `latest` tag is provided for convenient manual pulls only.

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

Follow [Production deployment setup](PRODUCTION_DEPLOYMENT.md#required-repository-setup). Missing native approval or protection blocks production. The GitHub connector cannot configure environment administration.

Environment variables:

- `PRODUCTION_URL`: user-facing production URL
- `PRODUCTION_HEALTHCHECK_URL`: HTTPS Django readiness endpoint ending in `/health/ready/`

Protected environment secrets:

- `PRODUCTION_DEPLOY_WEBHOOK_URL`
- `PRODUCTION_DEPLOY_TOKEN`
- `PRODUCTION_BACKUP_WEBHOOK_URL`
- `PRODUCTION_BACKUP_TOKEN`
- `PRODUCTION_STUDENT_EMAIL`
- `PRODUCTION_STUDENT_PASSWORD`

Also configure `PRODUCTION_COURSE_PATH` and `PRODUCTION_LESSON_PATH` as environment variables for real protected fixture content. Keep all production secrets exclusively in this environment; no repository/organisation copies and no `secrets: inherit`.

Configure at least one required reviewer, disable administrator bypass where policy permits, and restrict the deployment branch to `main`. GitHub stores the secrets; do not place their values in repository variables, workflow YAML, deployment responses or logs.

The workflow cannot create environment reviewers from source code. Production approval becomes enforceable only after the repository owner configures required reviewers in the GitHub environment settings.

## Release flow

1. A pull request must pass every quality and security gate.
2. Merging to `main` repeats the gates and publishes `docker.io/bethuelm/amaris-mathematics-academy:<commit-sha>` and `:latest`.
3. The workflow records the currently active immutable release (version N), deploys the SHA-tagged candidate (version N+1), and checks both deployment state and readiness.
4. If staging is unhealthy or reports the wrong Git SHA or Docker tag, the workflow rolls back to the exact version N image and verifies that version N is active and healthy.
5. A successful main release reaches the production approval gate; a manual main run must explicitly enable `deploy_production`.
6. GitHub pauses for required production reviewers. The job then verifies native protection and approval for the exact run/SHA.
7. The production acceptance manifest must show all 20 criteria as passed, evidenced, dated and reviewer-approved.
8. Recheck the published registry digest; acquire the hosting lease; prove N is healthy; create and verify a fresh backup for every release; inspect migration compatibility.
9. Deploy by digest, run safe migrations, verify health, run public smoke and the critical student journey, and monitor for five minutes before commit. Any failure after deployment attempts verified rollback to N and leaves the workflow failed.
10. Both environments retain deployment records for 90 days. Production includes approval, recovery ID, digest identities, phase timestamps and outcome; export to controlled audit storage for longer retention.

The authoritative evidence requirements and current pre-production status are in [`ACCEPTANCE_CRITERIA.md`](ACCEPTANCE_CRITERIA.md). A build or manual approval cannot bypass the acceptance verifier.

## Staging webhook contract (v1)

Production requires the extended [API v2 contract](PRODUCTION_DEPLOYMENT.md#hosting-adapter-api-v2), including safe migrations, fresh backups, monitoring and a durable rollback watchdog. The following v1 contract remains for staging.

The hosting platform must expose an authenticated HTTPS webhook supporting exactly three actions: `status`, `deploy` and `rollback`. It must reject arbitrary shell commands and unapproved image repositories.

A status request contains:

```json
{
  "action": "status",
  "environment": "staging",
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
  "environment": "staging",
  "image": "docker.io/bethuelm/amaris-mathematics-academy:<full-commit-sha>",
  "release_sha": "<full-commit-sha>"
}
```

The adapter must return HTTP 2xx only after accepting the action. It must set `APP_RELEASE_GIT_SHA` and `APP_RELEASE_IMAGE_TAG` on the web container. The Django `/health/ready/` response publishes these two non-secret identifiers, allowing the workflow to prove which release is healthy.

For `deploy`, retain at least the previous two known-good immutable images and configurations. For `rollback`, atomically restore the exact `image` and `release_sha` in the request. A rollback is not considered successful merely because the webhook returned 2xx: the status response and readiness endpoint must both report version N before the workflow records recovery.

Production backups and their transaction-bound evidence are specified in the API v2 contract.

## Staging rollback drill

Run the workflow manually with **rollback_test** enabled and **deploy_production** disabled. The job records version N, deploys N+1, deliberately enters the rollback path, restores N, and passes only when status and readiness both identify N. Use a new commit so N+1 differs from the staging release already active. A successful drill produces a `rollback_test_passed` deployment record; it never promotes the candidate to production.

## Recovery and operations

- Keep the previous two known-good images available for rapid rollback.
- Never reuse the mutable `latest` tag for a production decision; release by commit SHA.
- Database migrations must follow the expand/migrate/contract pattern described in the disaster-recovery runbook.
- When a schema is not backwards compatible, stop the release and use a reviewed maintenance procedure instead of relying on automatic rollback.
- Review Lighthouse reports for 14 days and SBOM artifacts for 30 days; retain production release and approval records according to the organisation's audit policy.

The broader database restoration, Redis/Celery recovery and RPO/RTO policy is in [`backend/docs/DISASTER_RECOVERY.md`](../backend/docs/DISASTER_RECOVERY.md).

