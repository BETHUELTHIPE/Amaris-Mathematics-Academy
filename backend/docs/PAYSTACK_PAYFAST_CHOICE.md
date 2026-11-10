# Student payment gateway choice — draft staging release

Amaris supports PayFast (existing default) and an optional Paystack hosted checkout for both paid courses and 1-hour Zoom class reservations. The browser never supplies the payable amount.

## Credentials / safe rollout
- Keep `PAYSTACK_ENABLED=false` by default on both the Django backend and student frontend. When false, the original PayFast checkout remains the default; only enable the two-provider selector after verified staging acceptance.
- Set `PAYSTACK_SECRET_KEY=sk_test_...` only in Render **staging** environment secrets; never commit it or paste it in chat. Live credentials must remain separate.
- Set `PUBLIC_SITE_URL` to the HTTPS staging student site; only Paystack-hosted authorization URLs are accepted.
- Configure Paystack webhook (test mode) as `https://<staging Django API>/api/v1/paystack/webhook/`.
- Existing PayFast variables and callbacks remain unchanged. Do not overwrite PayFast merchant secrets.
- Verify the Paystack webhook signing mode. The draft validates both legacy `x-paystack-signature` HMAC-SHA512 and timestamped `Paystack-Signature` with `PAYSTACK_WEBHOOK_SECRET=whsec_...` and five-minute replay tolerance; both additionally verify the transaction through Paystack API. Configure the webhook signing secret privately in staging if modern headers are used.
- Never grant enrollment or release Zoom links from browser redirects. Only verified webhook can settle.

## Before enabling
1. Black, Ruff, migrations (including 0009), Pytest/Django checks and existing PayFast tests all green.
2. Confirm Paystack merchant account is approved for South Africa (ZAR), webhook signature version, and secure keys.
3. Real Paystack **test-mode** transaction: initialize -> successful payment -> signed webhook -> server verify status, amount, currency, reference -> fulfillment; verify repeat callbacks do not duplicate.
4. Confirm a course enrollment, approved professional letterhead invoice archive/email, tutor/student/admin live-class confirmation, 30-minute reminder, and Zoom access after settlement. Ensure failed/cancelled/late/suspicious payments never fulfill.
5. Test expiry while provider charge succeeds: booking must not confirm; contact admin and perform refund/reconciliation.
6. Add operational monitoring for failed verification, outbox processing and payment reconciliation. Staging and broker services must be active.
7. Confirm Paystack fees and merchant identity, then separately authorize production rollout.

No production deploy or live payment is included in this draft.
