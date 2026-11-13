# Tutor leave and withdrawal / resignation forms

Approved, email-verified tutors use **Leave & resignation forms** in their private dashboard. Forms, saved PDFs and Admin emails use the academy letterhead, logo, contacts, Managing Director, navy/blue/gold accents and reference/footer. The shared renderer covers the other Django business emails in this release. The subscription-report PR also uses it; independent hosted Auth/provider templates are separate configuration.

## Submission and archive

- Leave: annual, sick, personal/family, study or other; first/last dates; inclusive **calendar days** (not paid-leave entitlement); reason; affected lessons/handover; contact number; typed signature; declaration.
- Resignation: proposed last teaching day, reason, handover, contact, typed signature and declaration. The proposed last day cannot be in the past when submitted. Leave may be retrospective for illness. Typed names record a declaration, not an identity-certified signature.
- Calendar dates are unchanged by time zones. Submission/review timestamps display in SAST. Identity/email come from verified authentication; clients cannot select another tutor, recipient or approval status.
- Submitted details and the original PDF are immutable. Admin decisions/notes are separate, with reviewer and timestamp. The original PDF always records the initial submission; the dashboard shows the current review status.
- Additive migration 0025 follows 0024. It enables RLS and revokes PUBLIC/anon/authenticated table grants. Reconcile migration leaves with other unmerged features before integration.
- PDFs use the default private **CMS bucket** (`amaris-cms-files`), under `tutor-personnel/<Django-user-id>/<form-uuid>/<kind>.pdf`. Metadata remains in Django. Student storage is not used. History is paginated ten records at a time.
- Owner-only downloads use `/api/v1/tutor/forms/<uuid>/pdf/`, proxied through `/api/tutor/forms/<uuid>/pdf`. They verify SHA-256 and set private/no-store, nosniff and attachment headers. No public URL or raw object key is exposed. The letterhead/confidential footer repeat on every PDF page.

## Django Admin

**Tutor leave / resignation forms** provides type/status/delivery filters, tutor search, submitted details, private PDFs and review notes visible to the tutor. Admin approves/declines leave or acknowledges resignation; ordinary Django Admin change logs apply.

Staff need model permissions to review and cannot belong to Tutors unless superuser. Tutor staff with view permission can only see/download their own forms and cannot review them. There is no Admin create/delete or tutor edit endpoint. Submission does not cancel lessons, remove slots, disable accounts, change payouts or deduct leave balances. Admin coordinates those steps separately.

## Admin email delivery

The saved database row is a durable outbox. A request saves the PDF and row before returning success, without SMTP. Tutor-scoped idempotency keys return the original row/PDF after an interrupted retry; a changed payload with the same key returns 409. Failed registration attempts clean up the new PDF where possible; reconcile private orphan files if cleanup fails.

An exact resignation retry still returns its original notice if the request crosses midnight after the proposed last teaching day. Only new notices are checked against today's SAST date, inside the same locked transaction after resolving a previous submission. New past-dated notices remain invalid.

Beat runs `content.tutor_personnel_tasks.deliver_tutor_personnel_forms` every 30 seconds on the existing notifications queue, in batches of 25. A row lock and committed sending claim precede SMTP. The letterhead email includes all submitted details, the exact archived letterhead PDF and stable Message-ID. No storage key or bearer URL is emailed.

Recipient: `TUTOR_PERSONNEL_ADMIN_EMAIL`, otherwise trusted `SiteSettings.email`, otherwise the academy default. The sender rechecks this address; changes hold the confidential form for review. Known SMTP rejection retries with exponential delay, at most five attempts. Unknown outcomes, stale sending claims older than an hour and corrupt PDFs require review. A crash/database acknowledgement failure after SMTP does not trigger a blind resend. Provider acceptance is not inbox receipt.

After independently confirming the provider **did not accept** the stable Message-ID:

```sh
python manage.py review_tutor_personnel_email FORM_UUID --confirm-not-accepted
```

Only unsent review records can be requeued; active sending claims cannot. Fix archive/recipient configuration first. Never requeue an accepted or uncertain email just because an inbox has not been checked.

## Enablement and acceptance

`TUTOR_PERSONNEL_FORMS_ENABLED=false` by default; production enablement requires existing private Supabase S3 configuration. Verify the CMS bucket is private and selected. `TUTOR_PERSONNEL_ADMIN_EMAIL` is optional. The dashboard capability hides forms against older/disabled backends; POST enforces the flag. Existing saved forms remain readable by their owner.

In staging: apply the additive migration, verify private storage and owner/staff isolation, submit labelled synthetic leave and resignation forms, download PDFs, confirm worker/Beat processing and actual Admin inbox receipt with exact PDF bytes, review leave/acknowledge resignation, then check dashboard status/notes. Confirm no lessons/accounts changed on submission. Mocked storage/SMTP and isolated browser tests do not establish live acceptance. No paid infrastructure is introduced.
