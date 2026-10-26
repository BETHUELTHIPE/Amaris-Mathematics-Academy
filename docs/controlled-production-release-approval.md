# Controlled Amaris production releases: staging success is NOT authorization

**Policy:** A passing staging pipeline is necessary but never sufficient for a production merge, database change, Auth configuration change, or deployment. The owner must separately approve each exact release SHA **after** reviewing the corresponding acceptance evidence. Never infer approval from a previous request, past successful deployment, green CI, or an uploaded report.

## Verified infrastructure drift on 26 October 2026

- **Live student frontend Render** `srv-damn6d2d0e5s73d02j5g` tracks `render-live-current-20260918` and currently has **autoDeploy OFF**. Retain that setting.
- **Production Django backend Render** `srv-dapn6b3tqb8s73d3r7n0` tracks `production-release-20260923`, but the live service reports **autoDeploy checksPass ON**. The repository `render.yaml` declares `autoDeployTrigger: off`; the deployed service has drifted from the intended policy. This MUST be disabled in Render by an explicitly authorized production configuration action before further backend merges. This PR intentionally does **not** change the live Render service.
- GitHub ruleset [25894039](https://github.com/BETHUELTHIPE/Amaris-Mathematics-Academy/rules/25894039) protects `main` and the live-student frontend branch, but its read-back reports **zero required approving reviews and an empty required-status-check list**. This is insufficient for the owner's explicit-approval policy. Admin settings require an authorized human to change. Ruleset changes are **not** performed by this PR.
- The connected GitHub tooling cannot modify repository branch rulesets or inspect GitHub environment reviewer requirements, so do not assert that reviewers are already configured.

## Code-level release safeguard in this PR

`.github/workflows/quality-release.yml` retains manual-only `workflow_dispatch` production deployment, which additionally requires `deploy_production=true`. The production job runs in the `production` GitHub Environment and now calls `scripts/release/verify_manual_production_approval.py` **before** approval evidence processing, migration backup or any deployment.

The gate fails closed unless:

1. Workflow was manually dispatched against **protected main** in the correct repository.
2. The environment's `PRODUCTION_APPROVED_SHA` equals the actual workflow SHA and the owner's distinct `production_approval_reference` input equals environment `PRODUCTION_APPROVAL_REFERENCE`.
3. A completed successful **Live Staging Acceptance** workflow is independently read from GitHub's API using `PRODUCTION_STAGING_RUN_ID` and its `head_sha` matches that exact release SHA.
4. A completed successful, explicitly manually dispatched **Genuine Production Public Backup** workflow is independently read using `PRODUCTION_BACKUP_RUN_ID`, matches the exact SHA, and comes from the named backup workflow.
5. `PRODUCTION_ROLLBACK_SHA` is a valid distinct previously tested commit.
6. The existing `publish-image`, `deploy-staging` dependencies and release acceptance criteria also pass. Never deploy when any check is failing, missing, stale or unverified.

The gate does **not** automatically merge or deploy changes. It checks recorded evidence only. A reviewer must still verify the staged Render service actually runs the approved SHA and the backup artifact has a successful isolated restore; a passing workflow alone does not replace inspecting those artifacts.

## Configuration to perform only after separate owner approval

### GitHub branch protection

1. Open [Amaris production ruleset](https://github.com/BETHUELTHIPE/Amaris-Mathematics-Academy/rules/25894039).
2. Require **at least 1 approving review from an independent authorized reviewer**, dismiss stale reviews on new commits, and disallow bypass.
3. Require appropriate **named checks on the exact PR head**; set up separate branch-specific rulesets if the backend and frontend use different required checks. Never require a check that is absent on the target branch without first adding the corresponding workflow, as this could block all releases.
4. Include `production-release-20260923` in a protected production branch ruleset with required PR reviews, status checks and no bypass. The currently inspected ruleset does not include this backend branch.
5. Configure the **production GitHub Environment** with required reviewers and prevent self-review where the GitHub plan permits. Do not store secrets as approval markers.

### Disable backend auto deployment on Render

1. Open [Render service](https://dashboard.render.com/web/srv-dapn6b3tqb8s73d3r7n0) → **Settings** → **Build & Deploy**.
2. Set **Auto-Deploy** to **Off** and save. Recheck through the Render connector that `autoDeployTrigger=off`.
3. Retain live-student frontend auto-deploy Off. Do not modify the database, worker, scheduler, SMTP, environment variables or paid service count while adjusting this release control.

### One-time approval variables for each explicitly approved SHA

After passing staging browser tests, confirming archive/restore, and reviewing the rollback, manually set these **production environment variables** at [GitHub production environment settings](https://github.com/BETHUELTHIPE/Amaris-Mathematics-Academy/settings/environments):

| Variable | Content |
| --- | --- |
| `PRODUCTION_APPROVED_SHA` | Exact 40-character reviewed commit SHA |
| `PRODUCTION_APPROVAL_REFERENCE` | Unique human approval reference tied to the release |
| `PRODUCTION_STAGING_RUN_ID` | Exact successful staging acceptance Actions run ID |
| `PRODUCTION_BACKUP_RUN_ID` | Successful genuine encrypted public schema backup Actions run ID for that SHA |
| `PRODUCTION_ROLLBACK_SHA` | Previous healthy deployment commit SHA |

When the owner has **separately and explicitly approved** a release, use **Actions → Quality Gates and Release → Run workflow**, choose **main**, enter `deploy_production=true`, the matching `production_approval_reference`, and migration risk. Approve the GitHub production environment gate. After completion, clear or replace the approval variables so stale approvals cannot authorize later releases.

This control is additive to the mandatory health, payment, SMTP, private storage, restore, accessibility, security and rollback gates; it does not certify them.

## Current status

The code-level protection is in **a draft PR** only, not merged or active on `main` until independently approved. GitHub branch ruleset and Render auto-deploy changes require separately authorized administrator action. **Production remains unchanged by this proposal.**
