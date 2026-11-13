# Fortnightly Admin performance reports

This feature adds **Performance reports** to Django Admin's navigation, a private report archive, a dashboard with rankings and weekly breakdowns, a company-letterhead PDF and an automatic company-letterhead email to the configured Admin recipient. It uses the existing notifications worker/Beat queue; no paid infrastructure is created.

## What the report measures

| Indicator | Definition |
| --- | --- |
| Most booked tutors | Verified paid Zoom bookings, grouped by the assigned slot's tutor; ties share a rank |
| Booking context | Distinct booking learners, booked hours, base gross and recorded completed/due lessons; future lessons are not counted as overdue |
| Most requested topics | Verified paid video requests, grouped by curriculum, subject, normalised level/topic and request type |
| Topic context | Distinct learners, current outstanding queue, recorded delivery turnaround and previous-period change |
| Best-selling courses | Verified paid course purchases, distinct buyers, base gross and previous-period change |
| Video delivery leaders | Verified paid videos marked ready within the period, including orders paid in earlier periods |
| Follow-up opportunities | Approved active tutors with no new paid Zoom bookings, topic backlog, legacy/payment-review gaps and missing archived periods |
| Within-period trend | Two separate seven-day totals whose counts match the fortnight |

All financial metrics require positive ZAR value, a paid timestamp, server gateway verification and a matching stored payment environment. Pending, failed, cancelled, refunded, payment-review and unclassified records do not enter the rankings. Reporting uses the gateway-verification timestamp in half-open SAST calendar windows `[start, end)`. The previous comparison window is exactly 14 days earlier, queried using the same rules.

Only the top 20 tutor/topic/course groups and top ten video delivery leaders are displayed. Topic normalisation merges case and ordinary spaces/tabs/newlines; synonyms and distinct educational contexts stay separate. No student names/emails, instructions, banking details or provider credentials enter the snapshot, PDF or email. Bookings count orders, not hours; learners are distinct within each group, not added across services.

Popularity is one indicator of contribution. It depends on availability and exposure and does not establish teaching quality. Recorded completion status is not measured attendance. Use feedback and delivery review before making staffing decisions. Base gross is before fees, not profit or tutor payout; video priority add-ons and curriculum-subscription sales are excluded. The subscription feature is a separate pending branch and does not represent an individual course purchase.

Snapshots freeze the tutor assignment, course labels and statuses seen at generation. Later refunds or edits do not rewrite the archive. PostgreSQL archive generation uses a repeatable-read transaction; the unsaved Admin preview uses current records. This is an operations report, not a substitute for settlement or accounting reconciliation.

## Payment environment and historical data

New additive `payment_mode` fields on course Payment, LiveClassBooking and VideoRequest default to `unknown`, including a persistent database default so older application instances can still insert orders during deployment or rollback. Existing rows are deliberately not labelled live or sandbox by guesswork. Each current PayFast verification path records the server-selected environment after successful verification, in the existing transaction; duplicate callbacks do not reclassify old records. It does not change checkout pricing, payment authority, entitlement or tutor earnings.

Default reports are **live only**. Sandbox reports use a separate anchor/archive and clear SANDBOX labels. Unclassified positive verified orders are reported as an excluded data-quality count. Historical backfill requires independent provider evidence and a separate reviewed migration. When integrating other provider branches (for example Paystack), capture their verified environment before treating their sales as classified.

## Schedule and setup

Configuration:

```env
ADMIN_PERFORMANCE_REPORTS_ENABLED=false
ADMIN_PERFORMANCE_PAYMENT_MODE=live
ADMIN_PERFORMANCE_ADMIN_EMAIL=
ADMIN_PERFORMANCE_START_DATE=
```

The feature defaults off pending hosted acceptance. In production, enablement requires the existing private Supabase CMS storage configuration. Recipient selection is the validated `ADMIN_PERFORMANCE_ADMIN_EMAIL`, otherwise trusted SiteSettings email, otherwise the academy fallback. Clients cannot choose recipients. The configured start date must be ISO `YYYY-MM-DD`.

When enabled, the first scheduler invocation creates a persisted anchor for that environment: the supplied start date, or that day's date in SAST. It does not send a partial-period report. The first complete report becomes due **14 calendar days later at 09:00 SAST**, then every 14 days. Beat checks every ten minutes on the existing `notifications` queue; delivery follows the next eligible sweep. Restarting or redeploying does not reset the saved anchor. Changing the environment creates a separate schedule rather than mixing data.

After extended downtime, only the latest completed period is generated, avoiding an email flood. The dashboard/email shows how many earlier periods have no archive. An Admin preview of the last 14 completed calendar days is read-only: it does not create an archive, start the anchor or send an email.

## Privacy, persistence and delivery

Additive migration 0026 follows the parent PR's 0025; reconcile other unmerged migration leaves before integration. It adds the environment metadata, date/mode partial indexes and report/schedule tables. Both new tables enable RLS and revoke PUBLIC/anon/authenticated grants. No live schema/data is modified merely by opening this PR.

PDFs are saved in the existing private **amaris-cms-files** storage under `admin-performance/<mode>/<period>/<uuid>.pdf`. Download requires Admin authentication and report permission, checks the SHA-256 and returns no-store/nosniff/attachment headers. Superusers and non-tutor staff with `view_performancedigest` can view; ordinary tutors and students cannot, even if a tutor staff account accidentally receives that report permission. Report and schedule records are read-only in Admin; there is no public API.

One report per environment/period is enforced by a unique constraint and locked schedule. PDF + snapshot + outbox are saved before SMTP. Email includes the same archived PDF bytes, official letterhead, inline logo and a stable Message-ID. A committed sending claim precedes SMTP; overlapping workers cannot blindly send twice. Known rejections retry with bounded backoff; unknown outcomes, crashes after acceptance, stale sending claims, recipient/mode changes and corrupt archives require review. Provider acceptance is not actual inbox receipt.

After independently checking the stable Message-ID and confirming **non-acceptance**, an operator can requeue an unsent held record:

```sh
python manage.py review_performance_report_email REPORT_UUID --confirm-not-accepted
```

Correct recipient/archive configuration first; accepted or possibly active sends cannot be retried through this command. A failed archive/database transaction removes its new PDF where possible; reconcile private orphan objects if cleanup failed. No test uses real student records or sends a genuine external email.

## Acceptance and release

This is a focused branch based on the company-letterhead/tutor-workflow PR #443. Merge that dependency, reconcile migrations and retarget this PR to the release branch before production integration. The existing quality workflow additionally runs on the parent feature branch as a PR base; no gate is relaxed and deployment jobs stay protected.

Tests cover exact rankings/amounts, distinct learners, sandbox/legacy/refund exclusions, topic context, SAST boundaries, ties, future lessons, previous-period change, scheduling/restarts, frozen snapshots, private access, escaped HTML/PDF content, original PDF bytes, SMTP outcomes, row-lock concurrency/RLS and actual verified-mode capture on all three payment paths. The isolated visual workflow renders actual Django Admin/email HTML with clearly synthetic data; it does not establish hosted storage or inbox delivery.

Before enabling: verify the intended database/private CMS bucket, apply the compatible migration, run sandbox-labelled report acceptance with the existing worker/Beat and confirm the configured Admin inbox plus private PDF download. Preview live data only with trusted Admin access. Then set the live environment and anchor, enable on the authorised deployment and observe the first due report without duplicate delivery. Production/staging service restoration remains necessary where Render services are suspended; this code change does not resolve billing or resume paid services.
