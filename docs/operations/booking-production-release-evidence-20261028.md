# Amaris booking/payment release evidence ledger — 28 October 2026

**Decision: NO-GO for new production booking/payment code.** This records observed facts, not a substitution for genuine provider and external inbox acceptance. All observation queries and evidence-gathering actions were read-only against deployed applications; the existing production backend deployment is unchanged.

## 1. Genuine PayFast payment-to-settlement
- Staging Supabase `atyhhjwwxgzeurnwayay`: four confirmed live-class booking rows have `paid_at` and `gateway_verified_at`; one course payment is `paid` with `verification_source=payfast_server_verification`; one webhook is `processed`, with verification/processing timestamps.
- Production Supabase `epkcuseloinygkakxxdu`: no rows in the relevant booking/payment/invoice/outbox queries at audit time. This does not prove failed checkout; it means there is no production settlement record to certify.
- The whole integrated release still needs a **new real PayFast sandbox checkout** on deployed staging, provider-issued ITN, Django gateway settlement, repeat/duplicate callback and invoice/email correlation. Do not synthesize or forge provider notifications.

## 2. Approved letterhead, archived private PDFs
- Four confirmed staging bookings each match a PDF object in a **private** Supabase Storage bucket, with recorded object size.
- The genuine `INV-LIVE-20261025-30CCE97257.pdf` (74,999 bytes), independently opened from Gmail, is one-page A4 with academy logo, navy/gold professional letterhead, director/contact information, confirmed three-hour lesson and R750 amount.
- Older `INV-LIVE-20261024-0E3E7DA24A.pdf` (2,240 bytes) is a legacy plain-layout invoice; it lacks the approved PDF Author metadata and professional letterhead. Do not re-attach this as an approved invoice, and do not secretly overwrite or delete the original issued artefact. PR implementing fail-closed archive checks: #408. A separate audited corrective reissue for this old invoice remains a follow-up.

## 3. Three independently received email messages
- Staging class confirmations show all four student/tutor/admin **dispatch markers**.
- Gmail has matching attached PDFs on the tutor and administrator confirmations of the three-hour booking, but **both are addressed to the same connected QA mailbox** `bethuelmoukangwe8@gmail.com`. This does not prove delivery to independent production tutor/admin recipients.
- The student recipient `bethuelmoukangwe30@gmail.com` is not the connected inbox; sender dispatch alone does not independently certify that student's Inbox receipt.
- Acceptance needs **one newly paid staging booking**, three intended recipient addresses, Gmail/SMTP receipt evidence in each actual mailbox, matching booking/invoice references, and byte-level matching MIME PDF attachments (no raw credentials or customer data in workflow logs).

## 4. Celery worker, Beat scheduler and reminder timing
- Production Render backend runtime logs (28 October 2026 SAST) show Celery task reception/execution and Beat dispatch for `deliver_live_class_confirmation`, `deliver_live_class_reminder`, `archive_missing_invoice_pdfs`, and transactional emails. A successful task returning `0` does not mean a reminder was sent.
- Staging has two bookings with non-null `reminder_sent_at`, and four with `confirmation_sent_at`.
- Final acceptance requires a due booking whose reminder is triggered at the intended window, an actual recipient inbox message and a correctly recorded `reminder_sent_at`; confirm task retries and no duplicate messages.

## 5. Security, retries and duplicates
- PR #344 (three recipients/idempotent invoice) and PR #407 (official HTML letterhead) both passed Payment Security / Quality Gates / synthetic backup-and-restore CI at their own heads; both remained unmerged **drafts** when checked.
- These are *separate* heads; integrated changes, migration 0017, duplicate callbacks, webhook replay/retries, invoice write races, independent per-recipient delivery flags and negative authorization tests must pass together on a staging integration revision.
- PR #408 adds a guard against resending legacy archived generic PDFs; preserve canonical immutable keys and historical invoice originals.

## 6. Durable encrypted backup / restore / rollback
- **REAL backup-and-restore proof passed:** [GitHub run #40601163953](https://github.com/BETHUELTHIPE/Amaris-Mathematics-Academy/actions/runs/40601163953) exported the actual production `public` schema read-only, encrypted it with the protected recovery passphrase, decrypted and restored application data/constraints in a network-isolated PostgreSQL 17 instance and matched source/restored application row counts.
- Encrypted retained artifact: `encrypted-amaris-production-public-40601163953`, artifact ID `12779012080`, 40,372 bytes, expires 25 Jan 2027 (subject to repository retention). Verify a private off-GitHub recovery copy and key custodianship. **Supabase Auth and private Storage objects are NOT covered** by this public-schema backup.
- Verified currently live production backend Render revision `ce34fef5df1494d206582d9c7f0e14a6e7a5eb22`, deploy `dep-dbehv48473hc73dc1gv0`; previously deployed revision `1567e2a2c9092b8d9d7385a637c7acae52f78ce9`, deploy `dep-dbeh10vb9u1s739mig20`. These are recovery candidates, **not** evidence of a rehearsed application rollback.
- Before promoting an incompatible migration, prove rollback on isolated staging: previous application revision + forward-compatible schema OR rehearsed restoration, verify readiness and payment retry semantics, and document a recovery operator. Never restore test data over production.

## Operational blocker: staging Django SMTP
Staging preflight [run #40597232891](https://github.com/BETHUELTHIPE/Amaris-Mathematics-Academy/actions/runs/40597232891) reported `EMAIL_HOST_PASSWORD` and `DEFAULT_FROM_EMAIL`/sender missing. The separate protected *production* SMTP synthetic test [run #40597483908](https://github.com/BETHUELTHIPE/Amaris-Mathematics-Academy/actions/runs/40597483908) passed. A production SMTP success cannot certify staging or three actual inboxes; configure staging securely in Render without exposing or copying credentials into Git.

## Promotion policy
Do not merge/deploy booking/payment release PRs until all six evidence groups are complete, including real staging PayFast/specific invoice/three inbox receipts, worker and reminder timing, integrated security CI, retained backup and isolated rollback rehearsal. Production remains on the known live revision during this audit.
