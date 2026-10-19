# Amaris isolated staging — PayFast wallet booking / invoice / Gmail evidence

**Status:** protected manual acceptance is blocked until real staging SMTP credentials, private storage credentials, test student, tutor slot, and PayFast sandbox transaction exist. Do not claim end-to-end completion from local/mock tests.

## Boundaries
- Render staging backend: `srv-dam2iivcgkoc7383tq50` at `https://amaris-mathematics-academy-staging.onrender.com`.
- Supabase staging project: `atyhhjwwxgzeurnwayay`. Production project `epkcuseloinygkakxxdu` is forbidden.
- Real test recipient: `bethuelmoukangwe8@gmail.com`.
- Leave production services, production database, and real-money PayFast settings unchanged.
- Do not paste SMTP, Supabase S3, Gmail app passwords, database passwords, or PayFast keys into source, PR comments or logs.

## One-time setup outside source control
1. Configure staging Render SMTP with `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`, provider host/port/TLS, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, and `DEFAULT_FROM_EMAIL` using the authenticated sender. Save **and deploy**. If using Gmail, create a unique app password in the correct sender account; OAuth-connected Gmail in ChatGPT does **not** supply Django SMTP credentials.
2. Confirm the staging **student-private** bucket and separate **admin** bucket actually exist under the staging Supabase project and Django S3 keys can write/read. An S3 key that receives HTTP 403 is not accepted.
3. Configure the GitHub Actions **staging environment** secrets used by `.github/workflows/staging-liveclass-receipt-acceptance.yml`. Every secret is required; the gate stops without them. The encrypted secrets are scoped to staging; do not reuse production.
4. Verify the staging Celery notifications worker and beat are genuinely running and consuming `content.tasks.deliver_live_class_confirmation`. A manual task invocation from the acceptance workflow does **not** prove the automatic worker works. Do not provision a new paid worker without budget approval.
5. Register an isolated synthetic Supabase student with **this exact recipient email** and a private test password; create one published future tutor Zoom slot in staging. Check that the slot is priced server-side (R250 per hour).
6. Complete one **actual PayFast Sandbox wallet** checkout from the authenticated student interface at `https://sandbox.payfast.co.za/eng/process`. This is not a real-money charge. Check the merchant Sandbox ITN history to confirm the provider itself issued a notification to the staging `/api/v1/payfast/itn/` endpoint, and record the booking `LCB-...` reference and the actual numeric PayFast transaction ID. Do not create or approve a synthetic ITN.
7. Put the actual booking reference in the protected `STAGING_VERIFIED_BOOKING_REFERENCE` secret and the PayFast Sandbox ITN transaction ID in `STAGING_PAYFAST_SANDBOX_TRANSACTION_ID`. Once all prerequisites have been checked, set `STAGING_RECEIPT_ACCEPTANCE_ENABLED=true`.
8. Manually run **Staging real PayFast live-class email acceptance** on branch `ops/staging-known-good-af8709c-20261019`. Its guarded runner authenticates the student via staging Supabase, finds only the previously verified paid booking, checks the owner-only PDF and private Supabase object, calls Django's **actual** live-class confirmation task through SMTP, then checks the Gmail INBOX and attachment SHA-256. The runner never changes payment status or triggers a fake ITN.
9. Review the evidence artifact `staging-liveclass-real-smtp-gmail-evidence`. `AUTONOMOUS_CELERY_DELIVERY=NOT_VERIFIED` remains explicit until actual scheduled worker delivery has separately been observed.

## Release criteria

| Gate | Evidence required |
|---|---|
| Real PayFast sandbox checkout | Merchant sandbox transaction and provider-origin ITN, same reference and amount; Django `gateway_verified_at` and `provider_reference` set |
| Django paid booking | `CONFIRMED`, `paid_at`, `gateway_verified_at`, private Zoom link to its owner only |
| Invoice | PDF in staging private student bucket; authenticated owner 200; stranger/anonymous 404 or 401; unpaid order no PDF |
| Django SMTP | Genuine configured external SMTP `EMAIL_HOST*`, real `deliver_live_class_confirmation`, sent timestamp on successful provider acceptance |
| Gmail receipt | Actual INBOX message to approved recipient, subject with exact booking reference, attachment `<invoice_number>.pdf` with identical hash to private student archive |
| Autonomous worker | Beat/notifications worker observed delivering *without* manually triggering the task; separate from the manual acceptance gate |

**Evidence must never be claimed when the corresponding test was not executed.**

PayFast's Sandbox issues its own ITN; it can send notifications only once in some scenarios, so capture merchant history before proceeding. See [official PayFast developer documentation](https://developers.payfast.co.za/docs/itn-instant-transaction-notification/) for authoritative tests.
