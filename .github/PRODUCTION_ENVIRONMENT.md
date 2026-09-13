# Production GitHub Environment Policy

Production deployment is intentionally fail-closed and must use the GitHub environment named `production`.

## Required repository configuration

In **Settings -> Environments -> production**:

1. Configure required reviewers when the repository/account plan supports them. Use at least one reviewer who is authorized to approve a live release. Enable prevention of self-review when that option is available.
2. Restrict deployment branches/tags so production can only deploy from `main` (or the repository's explicitly approved release refs).
3. Store production deployment credentials as **environment secrets**, not repository or organization secrets:
   - `PRODUCTION_BACKUP_WEBHOOK_URL`
   - `PRODUCTION_BACKUP_TOKEN`
   - `PRODUCTION_DEPLOY_WEBHOOK_URL`
   - `PRODUCTION_DEPLOY_TOKEN`
4. Store production URLs as environment variables:
   - `PRODUCTION_URL`
   - `PRODUCTION_HEALTHCHECK_URL`
5. Remove any duplicate repository-level or organization-level copies of the production secrets after the environment-scoped values are confirmed.

## Workflow controls

`.github/workflows/quality-release.yml` enforces all of the following before the production job can run:

- manual `workflow_dispatch` only;
- `deploy_production=true`;
- explicit `production_approval=APPROVE_PRODUCTION` confirmation;
- source ref must be `refs/heads/main`;
- staging release gate must pass first;
- job is bound to the `production` environment;
- production secrets are referenced only from the production deployment job;
- production deployments share the repository-wide concurrency group `production-deployment` with `cancel-in-progress: false`, so a second production deployment waits instead of overlapping or cancelling the active deployment.

## Release rule

Do not promote to live production unless the `production` environment protection rules are configured, the required environment-scoped secrets and variables exist, all mandatory GitHub Actions checks pass, staging evidence is complete, and an authorized reviewer explicitly approves the environment deployment when GitHub supports that protection rule for the repository.
