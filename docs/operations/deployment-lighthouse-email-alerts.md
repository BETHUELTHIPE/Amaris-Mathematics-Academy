# Automatic Amaris deployment and Lighthouse email alerts

## Monitored results

- Strict mobile Lighthouse workflow and main Quality Gates: send PASSED, FAILED, CANCELLED or NOT RUN, including the overall CI result and GitHub log link. A failed CI build before Lighthouse is NOT RUN, not a misleading Lighthouse failure.
- Render production and staging backend/frontend: check every 15 minutes for successfully live, build failed, pre-deploy failed, update failed or canceled deployments. Email service, environment, commit, deployment ID and Render dashboard link.
- The first successful Render check records existing deployments without sending historical email. Subsequent checks remember sent IDs through a GitHub Actions cache.

## Configure once

In GitHub repository Settings -> Environments -> production -> Environment secrets, save:
1. AMARIS_NOTIFY_SMTP_USER: Gmail address that will send automated notifications.
2. AMARIS_NOTIFY_SMTP_APP_PASSWORD: 16-character Gmail app password (requires appropriate Google Account security settings). Never use the ordinary Gmail account password or paste it in chat.
3. AMARIS_NOTIFY_TO: comma-separated email addresses for the two administrator recipients.

The production backup workflows already use RENDER_API_KEY; this notification workflow reuses that secret read-only. If missing, add it to the same protected environment.

No new paid Render instance, webhook, or email provider is required.

## Send one test

After the notification PR is merged to main, open:
https://github.com/BETHUELTHIPE/Amaris-Mathematics-Academy/actions/workflows/amaris-release-email-alerts.yml

Select Run workflow, branch main, and select send_test_email. Verify the job prints PASS after SMTP acceptance and check both actual inboxes. A successful SMTP submission does not itself prove inbox delivery.

## Security and reliability

- The privileged workflow runs trusted main-branch notifier code and does not execute pull-request-controlled scripts or download untrusted PR artifacts.
- Reports include result status, service, commit SHA and links, never student names, booking/payment details, credentials or private logs.
- Render completion checks are approximately every 15 minutes; GitHub scheduled workflows may be delayed. Render native email notifications support failure, but not successful go-live emails.
- Checkpoint cache expiration or email transport interruption may cause occasional repeats or missed messages. This is best-effort monitoring, not guaranteed exactly-once delivery.
- If required mail secrets are missing, job logs say SETUP REQUIRED and do not claim an email was sent.
