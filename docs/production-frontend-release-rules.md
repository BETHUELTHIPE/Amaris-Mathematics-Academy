# Amaris production release controls — implementation and administrator activation

**Tracked by:** [Issue #386](https://github.com/BETHUELTHIPE/Amaris-Mathematics-Academy/issues/386)

**Frontend production branch:** `render-live-current-20260918`  
**Render production service:** `amaris-mathematics-academy-live-students`, `srv-damn6d2d0e5s73d02j5g`  
**Backend production branch:** `production-release-20260923` (separate release policy)  

## Immediate administrative actions — must happen before promoting this PR

1. In **Render Dashboard** open the production student frontend service, then **Settings → Auto-Deploy → Off**. Verify the Render service reports `autoDeployTrigger=off`. **Do not select On Commit or After CI Checks Pass** for the controlled manual-approval release process. Setting this control does not start a new app deployment.
2. In GitHub repository **Settings → Rules → Rulesets → New branch ruleset**, name it `Amaris student production — controlled release`. Select **Enforcement status: Active**, **Target branches: Include by pattern** `render-live-current-20260918` (only; `main` is a different branch).
3. Enable **Require a pull request before merging** (not just 'require a PR') and require at least **1 independent approval** from someone with write access; enable **dismiss stale reviews** and **resolve conversations before merging**. No bypass actors, including administrators or deploy bots. If there is only one contributor, add an independent reviewer rather than silently disabling required approval.
4. Enable **Require status checks to pass** and **Require branches to be up to date** (strict checks, latest commit). Select GitHub Actions as the expected source when available. Select the following **check/job names**, not just workflow names:
   - `Candidate TypeScript, lint, auth, booking, and dependency checks`
   - `Production branch ruleset enforcement active`
   - `Frontend auth type and unit checks`
   - `google-student-signin`
   - `applicant-journey`
   - `route-wide-chrome`
   - `Signed-in student UI (synthetic only)`
   - `backend-contract`
   - `browser`
   - `private-render-contracts`

   The mandatory gate workflow above runs **unconditionally for every PR into the live frontend branch**, with no path filters. Some historical E2E workflows are path-filtered; **remove path filters or make them unconditional before selecting them as required**, otherwise a docs-only PR can be blocked forever by missing checks. Do **not** treat skipped, cancelled, queued, or missing critical browser checks as verified. Require independent staging browser acceptance for sensitive user flows.
5. Turn on **Block force pushes** and **Restrict deletions**. Do not grant review/check bypass exceptions. Ensure stale approvals are dismissed on new commits.

## Controlled future production release

- Submit feature changes via a reviewed PR to the protected frontend branch; do not push directly.
- Run the above tests and full role-specific E2E on the **exact candidate SHA**, plus staging functional, mobile/accessibility, OAuth, verified/unverified email, password reset and signed OTP, tutor permission, protected booking, negative cases, payment and CSRF checks.
- Keep secrets out of CI output; no real customer account data or payment.
- After all checks and required approvals pass, merge the verified PR. With Render auto-deploy **Off**, this merge does not publish automatically.
- Review backup/rollback and deployment approval, then use Render **Manual Deploy → Deploy a specific commit** to deploy the exact **approved SHA** (or merge SHA only after its equivalence and checks are confirmed). Do not let Render deploy an unverified latest commit.
- Post-deploy smoke-test public and private routes. If critical issues appear, use Render's known-good rollback and document the incident.
- Check GitHub Rules page and live branch API `protected: true`, and check Render service `autoDeployTrigger: off` **again**. Treat failure to verify either as a release blocker.

## Verification and scope

The initial audit on **26 October 2026** found no GitHub rulesets, `protected=false` and Render `autoDeploy=commit`. The candidate workflow verifies branch protection and executes current unit, TypeScript, lint, and vulnerability tests, but **only administrators can activate repository Rules**. The connected GitHub App has content and PR permissions but not GitHub administration/ruleset write, and the installed Render connector does not expose the service settings update action. Repository code **cannot** independently enforce a GitHub ruleset or toggle Render's auto-deploy configuration.

PR code and successful CI alone are insufficient to claim enforcement is active. This document is intentionally not a production-deployment approval.
