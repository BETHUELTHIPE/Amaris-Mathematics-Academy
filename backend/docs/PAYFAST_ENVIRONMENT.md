# PayFast student checkout and tutor settlement

The operator selected **PayFast sandbox** and explicitly chose to retain the
existing seven-day settlement hold plus service-completion requirement on
15 October 2026. PayFast collects student payments for courses, live classes
and video requests. Tutor earnings are recorded only after authoritative
server verification; an eligible earning creates an `awaiting_provider`
payout. No bank transfer is performed and no payment receipt is fabricated.

## Managed configuration

Set merchant credentials privately in the **staging backend** Render service
`srv-dam2iivcgkoc7383tq50`, never in frontend public variables or Git:

- `PAYFAST_ENV=sandbox` (the existing `PAYFAST_MODE` name also works).
- `PAYFAST_MERCHANT_ID`, `PAYFAST_MERCHANT_KEY`, `PAYFAST_PASSPHRASE` from the
  sandbox account. Credentials for a live account are not sandbox credentials.
- `PUBLIC_API_URL=https://amaris-mathematics-academy-staging.onrender.com`.
- `PUBLIC_SITE_URL=https://amaris-mathematics-academy-staging-x4ax.onrender.com`.

If both environment names are present they must agree. Invalid or conflicting
values reject checkout/verification; synthetic acceptance completion also fails
closed. Course, class and video checkout use the same resolver as ITN validation.
The HTTP verifier rejects a missing or different merchant identity before
checking the signature and contacting PayFast's validation endpoint.

Rotate credentials exposed in chat in the appropriate PayFast dashboard, then
update Render privately. Do not copy staging credentials or sandbox mode onto
the production backend `srv-dapn6b3tqb8s73d3r7n0`. Code compatibility can deploy
without changing production merchant configuration. Direct-variable preflight
reports presence and a validated mode only; linked groups and secret files can
change the effective runtime environment and require separate verification.

## Why Split Payments remains disabled

PayFast Split Payments allocates funds at the original customer checkout to
one other **PayFast merchant account**. It does not implement this application's
delayed, fulfillment-dependent bank-transfer workflow. A tutor bank number or
admin phone number is not a split-payment merchant identifier. No `setup`
split payload is added by this release.

Keep earnings pending until a separately verified delayed-disbursement
integration is available. Confirmation that a student paid is not evidence
that the tutor's bank received a transfer. PayFast sandbox uses virtual funds
and does not send its own confirmation email; Amaris invoice and reminder
emails need the application mail configuration and running job workers.

## Verification and limits

Incoming ITN signatures use all posted fields except `signature`, preserving
their order, empty values and whitespace. Do not reuse the checkout signature
normalizer, which intentionally omits empty fields and trims checkout values.
The server-to-server validation request must carry the same notification
parameter string without the signature or passphrase. A fixed vector in
`content.test_payfast_configuration` covers this difference, PHP-compatible
URL encoding and rejection if an empty signed field is removed.

The `amaris.payfast` logger emits only fixed callback outcomes and verification
stages. It excludes IPs, identifiers, payloads, credentials and signatures; ASGI
request access logging stays disabled. A `received` outcome distinguishes an
ITN reaching Django from a provider-side delivery problem. This is diagnostic
evidence, not proof of payment unless authoritative verification succeeds.

Automated tests use synthetic credentials and mocked HTTP validation, check
both mode names, conflicting settings, merchant binding, signatures,
idempotent invoices/notifications and tutor settlement holds. These tests do
not establish that an actual PayFast sandbox account accepted a checkout, an
ITN reached Render, a live inbox received an Amaris email, or a tutor was paid.
Record each of those separately when observed. No schema migration is needed.

Official references:

- [PayFast Split Payments setup](https://support.payfast.help/portal/en/kb/articles/how-do-i-enable-split-payments-20-9-2022)
- [Split payment restrictions](https://support.payfast.help/portal/en/kb/articles/can-i-split-a-payment-20-9-2022)
- [Sandbox account credentials](https://support.payfast.help/portal/en/kb/articles/how-do-i-make-test-payments-in-sandbox-mode-20-9-2022)
- [Sandbox behavior](https://support.payfast.help/portal/en/kb/articles/what-is-the-difference-between-the-sandbox-and-the-live-payfast-system-20-9-2022)
