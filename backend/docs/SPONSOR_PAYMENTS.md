# Sponsor payment choice: PayFast and Paystack

Sponsors can enter a contribution in rand (R10–R1,000,000), choose PayFast or
Paystack, review the amount/reference and continue to the provider's hosted
checkout. Card and banking details are entered on the provider's page. The
application does not collect or store those details.

Both provider choices appear in the sponsor workspace. Unconfigured or paused
providers are disabled with an unavailable message. The private design preview
shows the choices with test labels and disables the checkout button. It cannot
create or process payments.

## Configuration and activation

These server-side flags default to false:

- `SPONSOR_PAYMENTS_ENABLED`
- `SPONSOR_PAYFAST_ENABLED`
- `SPONSOR_PAYSTACK_ENABLED`

Set `PUBLIC_SITE_URL` and `PUBLIC_API_URL` to the same environment's HTTPS
frontend and Django API origins. Apply additive migration
`0021_sponsor_payment_gateways` after the sponsor dashboard's 0020 migration.
It adds nullable/defaulted columns and verification/uniqueness constraints;
existing manual contributions remain manual records. Existing table RLS and
revoked Data API privileges remain in force.

PayFast uses the existing `PAYFAST_MODE`/`PAYFAST_ENV` and merchant settings.
The two mode settings must agree. Sandbox is stored as `test`; live is stored as
`live`. Live merchant credentials are required for live checkout. The existing
`/api/v1/payfast/itn/` endpoint now routes `SC-` references to sponsor settlement
while preserving course, Zoom and video handlers.

Paystack requires `PAYSTACK_MODE=test` or `live`, and a corresponding
`PAYSTACK_SECRET_KEY` prefix (`sk_test_`/`sk_live_`). Keep all secret values in
protected backend environment variables. Set the sponsor webhook URL to:

`https://<this-environment-api>/api/v1/sponsor/paystack/webhook/`

Configure `PAYSTACK_WEBHOOK_SECRET` with the provider-issued `whsec_` signing
secret. Optional `PAYSTACK_WEBHOOK_SECRET_PREVIOUS` supports the provider's
rotation overlap. Modern `Paystack-Signature` headers are verified over the raw
body with the signed timestamp and a 300-second tolerance. Invalid or stale
modern signatures cannot fall back to legacy verification.

For an integration that has not enabled modern signatures yet, explicitly set
`PAYSTACK_ALLOW_LEGACY_WEBHOOK_SIGNATURE=true` and leave both modern webhook
secrets unset. This checks the legacy `x-paystack-signature` HMAC against the
server secret key. Move to modern signatures once they are available. Merely
having an API secret does not silently enable legacy verification.

The sponsor handler is separate from the student Paystack draft in PR #437;
it does not depend on that draft's older student models or migration. Configure
this endpoint for sponsor transactions and preserve any student endpoint when
that feature is adopted.

## Verification and accounting

Checkout is a POST action protected by the existing verified session and
administrator-approved SponsorAccount. The backend takes payer email from its
validated Auth response. Currency is fixed to ZAR. Sponsor ID, return URL,
callback origin and paid state are never accepted from browser input.

A persisted idempotency key binds one sponsor, amount, provider and environment
to a generated `SC-` reference. Repeated requests reuse the same contribution;
changing the amount/provider with the same key is rejected. A Paystack network
failure after initialization starts leaves a pending review record and does
not blindly initialize the same reference again. Its reference remains visible
in contribution history. Check history before starting another payment.

PayFast verifies the original ITN signature, merchant and provider validation
response, then checks the stored amount, provider and environment. Paystack
verifies webhook origin and independently fetches the transaction from the
provider API, checking successful status, exact reference, ZAR cents, environment,
payer email and transaction ID. Redirects/cancellation query parameters never
mark a payment paid. Authenticated sponsors can explicitly request a Paystack
verification from their own payment-status page.

Rows are locked during settlement; a database constraint prevents reuse of a
provider transaction ID within a provider/environment. Duplicate success
callbacks preserve the first receipt time. Delayed failed/cancelled messages
do not undo received funding. Existing callbacks continue to be verified when
new-checkout flags are paused. Do not change gateway environments while
unresolved transactions are outstanding.

Pending/failed gateway checkouts are distinct from manually recorded pledges.
Test receipts are labelled in history, status pages and CSV exports and are
excluded from received funding, annual goals and giving charts. Gateway-backed
financial fields are read-only in Django Admin; operators cannot simply mark
an unverified online payment received. Refunds and disputes require independent
merchant reconciliation and a controlled accounting update; this feature does
not initiate refunds or infer them from browser input.

## Release evidence and remaining acceptance

Local synthetic tests cover both provider choices, amount tampering, ownership,
idempotency, signed callbacks, raw-body/timestamp checks, secret rotation,
independent verification, duplicate/concurrent settlement, test/live separation,
unsafe hosted URLs, initialization uncertainty and funding totals. Existing
payment tests exercise the preserved PayFast verifier and routing.

A mocked test suite is not a genuine provider payment. Before enabling real
checkout, restore isolated staging and complete a genuine PayFast sandbox and
Paystack test-mode payment through their hosted pages, verifying callbacks,
private sponsor history, totals, repeated notifications and reconciliation.
Check the mobile/desktop form and return pages. Live enablement additionally
requires merchant readiness and a specifically authorised controlled live test.
No merchant credentials, real payments or production data were used in this
implementation task.

Provider references consulted on 11 November 2026:
- https://paystack.com/docs/api/transaction/
- https://paystack.com/docs/payments/webhooks/
- https://developers.payfast.co.za/docs

Final local verification on 11 November 2026: 310 backend tests completed,
307 passed and three Redis-dependent checks were skipped. This includes 25
sponsor payment tests and the 11 existing sponsor dashboard tests. All 86
frontend tests passed, including 12 sponsor render/security tests. Frontend
production build, TypeScript, backend Ruff/Black/Mypy, migration drift and
OpenAPI checks passed. Django deployment checks also passed with isolated
production-style settings and an ephemeral secret. The repository still targets
Python 3.13/PostgreSQL 17 in CI; local tests used Python 3.12/PostgreSQL 16.2.
Frontend lint has no errors and two pre-existing warnings in unrelated files.
Real provider payment, merchant readiness and browser acceptance remain pending.
