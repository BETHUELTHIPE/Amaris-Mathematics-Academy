# Production incident response

The production incident path is deliberately separated from normal application traffic
and from release promotion.

## Runtime exception collector

Set the following on the deployed Django/Celery runtime:

- `APP_ENVIRONMENT=production`
- `INCIDENT_AUTOMATION_ENABLED=true`
- `INCIDENT_DEDUP_SECONDS=600`
- `INCIDENT_GITHUB_REPOSITORY=BETHUELTHIPE/Amaris-Mathematics-Academy`
- `INCIDENT_GITHUB_TOKEN=<dedicated fine-grained token or GitHub App token>`

The token should be limited to this repository and only the minimum permission needed to
create a repository-dispatch event. The collector excludes request bodies, query strings,
cookies, Authorization headers, user objects, exception messages, local variables and
source lines.

The release image embeds the exact Git SHA in `RELEASE_SHA`; incident fingerprints can
therefore be tied to the immutable image that produced them.

## Repository variables

Configure these GitHub repository or environment variables as appropriate:

- `PRODUCTION_HEALTHCHECK_URL` — HTTPS readiness endpoint.
- `PRODUCTION_URL` — public production URL.
- `PRODUCTION_AUTO_ROLLBACK` — set to `true` only after the rollback-target handler is
  proven in staging.
- `INCIDENT_AUTO_REVERT_PR` — set to `true` to allow a conservative draft revert PR
  when the failing release is exactly the current single-parent `main` commit.
- `INCIDENT_EMAIL_ENABLED` — set to `true` after SMTP configuration is verified.
- `INCIDENT_EMAIL_TO`, `INCIDENT_EMAIL_FROM`, `INCIDENT_SMTP_HOST`,
  `INCIDENT_SMTP_PORT`.
- `INCIDENT_COMPANY_NAME`, `INCIDENT_COMPANY_LOGO_URL`,
  `INCIDENT_COMPANY_PHONE`, `INCIDENT_COMPANY_EMAIL`,
  `INCIDENT_COMPANY_WEBSITE`, `INCIDENT_COMPANY_ADDRESS`.

## Repository secrets

- `PRODUCTION_DEPLOY_WEBHOOK_URL`
- `PRODUCTION_DEPLOY_TOKEN`
- `INCIDENT_SMTP_USERNAME`
- `INCIDENT_SMTP_PASSWORD`
- `INCIDENT_BOT_TOKEN` — optional fine-grained token used only to create a draft
  remediation PR. Without this token, incident issue creation and rollback response still
  work, but the draft revert PR is skipped.

The incident bot token must never be written to files or logs.

## Rollback-target host contract

The production deployment webhook host must configure
`ROLLBACK_TARGET_ACTION_EXECUTABLE` as an absolute executable path. It receives JSON on
stdin and must return JSON like:

```json
{
  "status": "succeeded",
  "image": "docker.io/bethuelm/amaris-mathematics-academy:<40-char-git-sha>",
  "release_sha": "<same-40-char-git-sha>",
  "rollback_safe": true
}
```

`rollback_safe` must be calculated by the deployment host from real release and database
state. If it is absent or false, the automatic rollback job stops without changing
production.

## Response sequence

1. Django exceptions are sanitized, deduplicated and dispatched asynchronously, while the
   same sanitized event is emitted to the application log.
2. GitHub's scheduled production monitor probes the HTTPS health endpoint twice before
   dispatching a health incident.
3. The incident response workflow sanitizes the payload again and creates or updates a
   GitHub issue.
4. An incident email is sent using the Amaris company letterhead when email alerts are
   enabled.
5. Critical incidents may request rollback only to the exact immutable host-provided
   rollback target and only when `rollback_safe=true`.
6. For a qualifying Django code regression, the bot may create a **draft** revert PR. It
   never merges that PR.
7. Any code remediation still goes through the existing pull-request Quality, Security,
   Docker/Nginx and frontend gates. Production promotion remains the normal protected
   staging-first release workflow.

No incident workflow contains a code path that merges a PR or deploys a new code fix
directly to production.
