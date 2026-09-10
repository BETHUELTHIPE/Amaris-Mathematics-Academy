# CI/CD quality gates and release controls

The `Quality Gates and Release` workflow validates every pull request to `main`, repeats the gates on `main`, publishes an immutable backend image only after all gates pass, deploys that image to staging, and allows production promotion only from a manual workflow run.

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
| Lighthouse | Performance 75%, accessibility 95%, best practices 90%, SEO 90% minimum |
| Dependency security | `pip-audit` and `npm audit` with critical findings blocking |
| Secret security | Full-history Gitleaks scan |
| Container quality | Docker Compose validation and a clean production-image build |
| Container security | Trivy blocks critical image vulnerabilities |
| Supply-chain record | CycloneDX JSON SBOM plus BuildKit provenance/SBOM attestations |

The container, image publishing and deployment jobs use normal successful-job dependencies. They do not use `always()`, so a failed or cancelled critical gate prevents image publication and deployment. Report uploads may use `always()` because they do not release software.

## GitHub repository protection

Configure the following settings in the GitHub repository before enabling deployments:

1. Protect `main` and require a pull request.
2. Require the `Python quality and Django checks`, `Frontend, accessibility, and Lighthouse`, `Dependency vulnerability gates`, `Repository secret scan`, and `Docker, Compose, image scan, and SBOM` checks.
3. Require branches to be current before merging and dismiss approvals when new commits arrive.
4. Prevent force pushes and branch deletion.
5. Enable GitHub secret scanning and push protection when available.
6. Allow GitHub Actions to write packages for the repository's GHCR image.

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
2. Merging to `main` repeats the gates and publishes `ghcr.io/bethuelthipe/amaris-mathematics-academy-backend:<commit-sha>`.
3. The immutable image is deployed to staging and its readiness endpoint is checked repeatedly.
4. If staging is unhealthy, the deployment webhook receives a rollback request and the workflow fails.
5. To deploy production, run `Quality Gates and Release` manually, enable **Promote the tested release to production**, and select the migration risk.
6. GitHub pauses the production job for its required environment reviewer.
7. The production-acceptance manifest must show all 20 criteria as passed, evidenced, dated and reviewer-approved.
8. A high-risk migration requires a successful backup response containing a non-empty `recovery_id` before deployment starts.
9. Production readiness is verified after deployment. A failed check requests rollback and leaves the workflow failed for investigation.

The authoritative evidence requirements and current pre-production status are in [`ACCEPTANCE_CRITERIA.md`](ACCEPTANCE_CRITERIA.md). A build or manual approval cannot bypass the acceptance verifier.

## Deployment webhook contract

The hosting platform must expose an authenticated HTTPS webhook. It receives a JSON request similar to:

```json
{
  "action": "deploy",
  "environment": "production",
  "image": "ghcr.io/bethuelthipe/amaris-mathematics-academy-backend:<commit-sha>",
  "release_sha": "<commit-sha>"
}
```

It must return HTTP 2xx only after the requested action has been accepted. For `deploy`, the platform must retain the previously healthy immutable image and configuration. For `rollback`, it must atomically restore that previous release. The webhook must not accept arbitrary shell commands from workflow input.

The backup webhook receives `action: backup` and `tag: pre-migration`. It must wait for a verified encrypted backup and return:

```json
{
  "status": "succeeded",
  "recovery_id": "opaque-recovery-point-reference"
}
```

A timeout, non-2xx result, failed status or missing recovery reference stops a high-risk production release.

## Recovery and operations

- Keep the previous two known-good images available for rapid rollback.
- Never reuse the mutable `latest` tag for a production decision; release by commit SHA.
- Database migrations must follow the expand/migrate/contract pattern described in the disaster-recovery runbook.
- When a schema is not backwards compatible, stop the release and use a reviewed maintenance procedure instead of relying on automatic rollback.
- Review Lighthouse reports for 14 days and SBOM artifacts for 30 days; retain production release and approval records according to the organisation's audit policy.

The broader database restoration, Redis/Celery recovery and RPO/RTO policy is in [`backend/docs/DISASTER_RECOVERY.md`](../backend/docs/DISASTER_RECOVERY.md).
