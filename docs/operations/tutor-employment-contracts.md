# Tutor employment contract workflow

## Purpose

Approved tutors complete a written South African employment agreement from the private tutor dashboard. The workflow is deliberately save-first:

1. Django verifies the Supabase email and approved `Tutors` group membership.
2. The server snapshots the active Admin-managed remuneration records, including the live-class percentage.
3. The tutor completes written particulars and four explicit declarations.
4. The server renders the tutor-signed PDF and saves it under `tutor-contracts/<tutor>/<contract>/` in the private `amaris-tutor-files` bucket.
5. Only after the archive and database transaction succeed is the delivery record eligible for the notification worker.
6. The worker attaches the exact archived bytes to the Super User email. It does not regenerate the document.
7. A Super User may accept or decline in Django Admin. Acceptance creates a separate immutable executed PDF; the tutor dashboard then downloads that countersigned copy.

No email is sent by the tutor's HTTP request. Retries use `(tutor, idempotency_key)` and a payload fingerprint, preventing duplicate PDFs and emails.

## Security and privacy controls

- The browser never supplies the tutor identity, recipient, percentages, status or statutory floor.
- Only the owning tutor can list or download a contract through the tutor API.
- Only a Django Super User can view, decide or countersign contracts in Admin.
- PDFs use private tutor storage. No public object URL is returned.
- Download responses are `private, no-store` and `nosniff`.
- SHA-256 verification blocks corrupt or replaced archives from download or email.
- The PostgreSQL migration enables RLS and removes `PUBLIC`, `anon` and `authenticated` table privileges. Django's trusted server connection remains the access path.
- Recipient drift, archive-integrity failures and uncertain SMTP outcomes are held for review instead of blind resend.

## Employment safeguards

Terms version `ZA-TUTOR-EMPLOYMENT-2026-03` uses **60% Admin (Academy) / 30% Tutor / 10% platform operating costs** of the gross service sale. For a R250 lesson this is R150 Admin, R75 Tutor and R25 platform operating costs, before lawful payroll deductions. The platform allocation is not an additional deduction from the tutor's 30% share. It treats the tutor as a part-time, variable-hours employee. The service-share schedule does not replace statutory wage protections.

The finance ledger's existing `academy_amount` is the combined business-retained 70% (60% Admin plus 10% platform), not an additional 70% on top of the platform allocation. Contract snapshots expose the two business allocations separately. This change does not introduce an expense-disbursement account, transfer money, change payment-provider fees, or rewrite historical earnings.

The PDF records:

- R30.23 per ordinary hour as the national minimum applying from 1 March 2026, with an automatic obligation to use a later higher legal rate;
- monthly pay no later than seven days after the pay period;
- PAYE, UIF, payslips and only lawful deductions;
- statutory hours, overtime, Sunday/public-holiday treatment and leave;
- the existing verified-payment, Zoom, completion and seven-day service-share settlement flow;
- POPIA, student confidentiality, safeguarding, professional conduct, equipment, materials, discipline and termination;
- access to fair process and statutory dispute forums.

The agreement must be reviewed by a South African labour-law practitioner before production activation. Review the minimum rate and the complete wording before 1 March 2027, and earlier whenever law, remuneration or booking/payment behavior changes.

## Required rollout sequence

1. Obtain legal approval and record the approved terms version.
2. Verify every tutor has exactly one active, non-overlapping `live_class` remuneration record, and all services included in a new employment contract use `tutor_percent=30.00`. The API blocks signing when the record is missing, ambiguous or conflicts with the 60% Admin / 30% Tutor / 10% platform policy. Do not silently overwrite existing signed contracts, previously earned amounts or historic percentages; agree any change prospectively and create the appropriately dated finance terms through the existing Admin workflow.
3. Deploy migration `0029_tutor_employment_contract` to staging.
4. Confirm `TUTOR_PERSONNEL_FORMS_ENABLED=true`, `TUTOR_PERSONNEL_ADMIN_EMAIL` is the intended Super User mailbox, and the notification worker/Beat process is running.
5. Confirm `SUPABASE_S3_TUTOR_BUCKET=amaris-tutor-files` and private S3 credentials on the web and worker services.
6. Perform staging acceptance with a synthetic tutor: sign, verify the tutor-signed PDF, process one Admin email, countersign, and verify the executed PDF from the tutor dashboard.
7. Verify no duplicate email occurs after repeating the same submission and delivery task.
8. Inspect logs and the Admin delivery status. Resolve any `review` record manually; never reset uncertain delivery to `queued` without checking the mailbox/provider.
9. Promote through the normal release workflow only after evidence is attached to the pull request.

## Rollback

Disable `TUTOR_PERSONNEL_FORMS_ENABLED` to stop new form and contract submissions. Existing records and private PDFs remain available for authorised review and retention. Do not delete the bucket objects or reverse the migration as a routine rollback; employment records may be subject to statutory retention duties.
