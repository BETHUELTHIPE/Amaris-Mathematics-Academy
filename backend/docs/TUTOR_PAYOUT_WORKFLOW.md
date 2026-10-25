# Tutor revenue sharing and payout readiness

Status: **feature branch / code review only**. Not deployed. No production database migration or real bank transfer has been performed.

## Business behaviour

* Superusers manage tutor accounts in Django Admin → Tutor payment profiles. Bank account numbers are **write-only** and Fernet-encrypted at rest using `TUTOR_BANK_FERNET_KEY`; only the last four digits are displayed. Set the key as a restricted Render secret and back it up separately. Do not change the key without decrypt/re-encrypt migration.
* Superusers record signed contracts in Django Admin → Tutor contracts. The **tutor** percentage is explicit; Academy receives the remainder. Examples: tutor 60% / Academy 40%, or tutor 50% / Academy 50%. Effective contract dates are checked and shares are snapshotted per sale so later contract edits cannot rewrite history.
* Courses require **exactly one** active Tutor course assignment. Unassigned/multiply-assigned courses are **not** silently attributed to someone else.
* Only server-side **verified PayFast COMPLETE** events create course, Zoom booking or topical-video tutor earnings. Client payment screenshots, redirects, success flags, and pending transactions do not count.
* The authenticated `/tutor/dashboard/` page displays verified paid order counts for videos, live bookings and courses, plus **attendance-confirmed** completed classes. It does not show student identity or account data.
* Topical video flow: `GET /api/v1/student/topical-videos/tutors/` and `POST /api/v1/student/topical-videos/checkout/` (student Supabase access token). The price is set server-side with `TUTOR_TOPICAL_VIDEO_PRICE_ZAR` (default R450). ITN routes references with `TVR-` and verifies the gateway, amount, learner and order. Fulfilment requires protected video delivery outside this first iteration.
* Once a paid service has been delivered and **seven days** have passed since verification, reconciliation marks income eligible. The service-delivery checks are: course enrollment active, live class marked COMPLETED by a superuser after reviewing Zoom attendance, video marked DELIVERED by a superuser after confirming the private asset.
* The ledger preserves references, total gross income, tutor share, Amaris share, eligibility and payout states. Refunds/cancellations hold or reverse **unpaid** earnings; paid out refunds require manual recovery/reconciliation with the tutor.

## What is intentionally not enabled

**No actual EFT or bank disbursement adapter is configured.** PayFast collects student payments but its incoming PayFast ITN is not bank-payout proof. `TutorPayout` is created in `awaiting_provider` state only. No code marks it paid merely because the student has paid or the payout was queued.

For South African automated payouts, Amaris must select and contract with a payout provider, verify tutors' banking details/KYC, implement provider-specific *idempotent transfer initiation*, a signed callback or status API for **independent settlement verification**, failure/reversal handling, transfer amount and destination checks, and safe reconciliation before the payout status can transition to `paid`. **Do not directly edit the payout status in the database.** Run sandbox tests and legal/accounting review before enabling live transfers. Payfast Split Payments may be an option where the tutor is a registered secondary merchant, but must be evaluated separately: a payment split is not bank-transfer proof.

A receipt email worker exists and **only sends** once a payout's trusted provider completion has been recorded with `confirmed_at` and `provider_reference`. The message contains the service reference, payout amount, provider transfer reference, date and masked destination, not a student's identity.

## Deployment checklist (all required)

1. Rotate previously exposed Supabase and Render credentials. Remove `DATABASE_URL` from frontend.
2. Verify a recoverable Supabase database backup and an isolated restoration test, with checksum and sign-off, before running migration `content.0008_tutor_finance`.
3. Configure the server-only `TUTOR_BANK_FERNET_KEY` (a newly generated Fernet key), SMTP credentials, notification worker and beat schedule. **Never** put the encryption key or bank details in GitHub, public frontend variables, logs or emails.
4. Create individual Django tutor users without `is_staff` / `is_superuser`. Create tutor profile, active signed contract(s), and course mapping(s). Bank details are admin-only.
5. Recheck gateway-verified purchase workflows with sandbox, including repeated ITNs, partial failures, mismatched amounts, multiple students, refunds, and delayed notifications. Review appropriate payout holds/fees, bank holidays, VAT and withholding treatment in contracts.
6. Test dashboard authorization, record ownership, privacy, accessibility/mobile layout and no PII in API responses. Verify only approved tutors can access their own page.
7. Add/verify real payout provider and sandbox callbacks, then test no double payouts, bank destination validation, manual holds, rejection/refunds, reconciliation, receipt emails and supporting accounting/export evidence. **Explicit approval** required before enabling real payouts.
8. Deploy only through protected release gate with staging → backup → migration → smoke tests → post-deploy checks → rollback procedure. **Do not** bypass the existing backup requirement.

## Known follow-up integrations

* Student-facing topical video purchase form and secure private delivery link are separate UI work. The backend checkout and verified payment ledger are present, but a request should not be advertised as fully live until the end-to-end student flow is tested.
* Zoom attendance may be imported from Zoom meeting reports after consent and tutor/session match checks; currently a superuser must review before marking COMPLETED.
* The dashboard is served securely from the Django backend at `/tutor/dashboard/`. No publicly exposed Next.js tutor identity is assumed.

## Revenue math

For a R250 online class at a **tutor 60%** contract, tutoring revenue accrual is **R150**, Academy share **R100**. For tutor 50% / Academy 50%, each accrues **R125**. These are **gross-sale splits before payment processing fees/taxes**, not settled bank balances. Fee/tax basis must be agreed in the contract before live payouts.
