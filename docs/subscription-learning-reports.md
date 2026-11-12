# End-of-subscription student learning reports

Applies to the four-month R3,800 and eight-month R7,600 curriculum subscriptions. The existing subscription payment verification and calendar-month expiry remain authoritative. This feature does not merge or deploy either subscription PR.

## What the student receives

One private, branded PDF attachment addressed only to the subscribing student, with a plain-text and HTML email summary:

- Name, subscription reference, chosen curriculum, plan, paid price and term dates.
- Confirmed attended hours/minutes, recorded scheduled time, full/partial/missed/cancelled/unrecorded counts and weekly totals.
- Each included session's date, scheduled start/end, actual joined/left times, tutor, subject, grade/level, topic, recorded outcomes, tutor feedback and practice recommendations.
- Dated lesson-open/progress milestones and the latest recorded progress for each course.
- South African time (Africa/Johannesburg, UTC+2) throughout.

Attendance percentage uses confirmed attended minutes divided by confirmed scheduled minutes (full, partial and missed sessions). Cancelled and unrecorded sessions are excluded. Zero records means unknown attendance, not proof that the student missed lessons. The report never multiplies a calendar term by an assumed number of weeks or converts playback position into attended hours. Course progress is student-reported and is not an assessment mark or verified video-watch time.

## Recording the source data

Authorised Django Admin staff enter included two-hour sessions under **Subscription sessions** and assign a tutor. This is an attendance ledger, not automatic slot allocation, Zoom meeting creation, a capacity reservation, or an additional paid hourly checkout. The academy must coordinate the two weekly sessions and invitations as described in `curriculum-subscriptions.md`.

After a session ends, its assigned, approved tutor may confirm full/partial/missed attendance through the authenticated API, or authorised staff may enter it in Admin. Actual attendance must be inside the two-hour session. Sessions must be inside a verified paid term; overlapping student/tutor ledger entries are rejected. Confirmation records the acting user and time. Every feedback field is explicitly student-facing; never enter internal or sensitive staff notes there. Admin cannot delete the dated ledger.

- `GET /api/v1/tutor/subscription-sessions/` lists the assigned tutor's latest 100 records without student email addresses.
- `PATCH /api/v1/tutor/subscription-sessions/<id>/attendance/` accepts `status`, `joined_at`, `left_at`, `learning_summary`, `tutor_feedback` and `next_steps`. Status is `attended`, `partial`, `absent` or `cancelled`. Full/partial attendance requires both timestamps; absent/cancelled must have neither. It does not accept a replacement student, subscription, tutor, or verification identity.

Authenticated lesson requests and the existing student progress endpoint capture lesson opens and meaningful progress changes for the relevant subscription. Course-access materialization alone does not create study activity. Repeated same-lesson opens within a day are coalesced. Repeated playback heartbeats do not create milestones. Historical browser visits, assessment results, unrecorded Zoom attendance, and activity before deployment are not fabricated. A dated snapshot survives enrollment reassignment during renewal.

## Automatic delivery and storage

`content.subscription_report_tasks.deliver_ended_subscription_reports` runs every ten minutes on the existing `notifications` queue, including notifications-only Beat. Each sweep handles at most 50 eligible ended terms, oldest first. Backlogs continue on later sweeps; the ten-minute interval is not a guaranteed delivery SLA for a large backlog. The task catches up after worker downtime.

Only active students with gateway-verified, paid subscriptions in the configured PayFast mode qualify, and only once `ends_at` is reached. Pending, refunded, future, inactive-student and cross-mode subscriptions are excluded. Eligibility and recipient identity are checked again immediately before sending. Recipients are not copied to tutors, administrators, other students or sponsors.

The immutable snapshot, private object key, SHA-256, recipient and delivery timestamps are recorded under **Subscription reports** in Django Admin. Objects use the configured `student_private` storage (the student **Amaris Mathematics Academy** Supabase bucket), under `<supabase-user-id>/subscriptions/reports/<report-uuid>.pdf`. Production enablement requires configured private Supabase S3 storage; it cannot fall back to a local disk. Never make this bucket public. The API serves a checked PDF through owner authentication and `private, no-store`, without exposing object keys or public URLs:

`GET /api/v1/student/subscriptions/<reference>/report/`

The existing subscription status/list output adds `report_ready` and `report_emailed_at`. Reports are archived before an email is attempted. Later attendance corrections do not silently replace an already-generated or emailed snapshot. Staff must review a correction request separately; automatic corrected-report versioning is not included.

## Send failures and duplicate protection

One report row per subscription and PostgreSQL row locks prevent concurrent workers from claiming the same report. A durable `sending` claim is committed **before SMTP**. A successful SMTP return records provider acceptance, which is not proof of inbox receipt.

Explicit SMTP rejection or a zero accepted-message count can retry with backoff, bounded to five attempts before review. An uncertain result (timeout/disconnect), changed recipient, invalid archive hash, or a sending claim older than one hour is held for review. A crash or database error after SMTP acceptance does not automatically resend. Exactly-once inbox delivery cannot be guaranteed by SMTP; the conservative review state avoids blind duplicates.

Only after inspecting provider logs and confirming a message was **not accepted**, an operator may requeue an ambiguous reviewed delivery older than one hour:

```sh
python manage.py review_subscription_report_delivery REPORT_UUID --confirm-not-accepted
```

This cannot requeue a recorded sent email. It does not bypass payment, expiry, current recipient or archive-integrity checks. Never use the command just because a student cannot find an email; first inspect delivery logs and spam folders.

## Release acceptance

1. Reconcile migration leaves if integrating other unmerged features. Apply additive migrations 0022 and 0023 in isolated staging. New report/session/activity tables enable RLS and revoke browser-role/public table and sequence grants. Django remains the authorization boundary; no browser Data API access is granted.
2. Confirm private student bucket configuration and owner-only API downloads; report keys must not resolve publicly.
3. Use synthetic verified subscriptions and authorised attendance records for both term lengths. Confirm SAST dates, full/partial/missed/cancelled/unrecorded cases and realistic multi-page PDF layout. Check separately purchased courses and other students never enter the report.
4. Set `SUBSCRIPTION_REPORTS_EMAIL_ENABLED=true` only in isolated staging with approved test recipients. Confirm the existing singleton Beat and notification worker consume the task. The default is false.
5. Observe an ended test term, an actual SMTP acceptance and a genuine recipient inbox with the exact archived PDF. Repeat sweeps and concurrent workers; no duplicate email. Exercise rejected/uncertain SMTP outcomes and worker recovery.
6. Enable production only with the reviewed application release, migrations, correct private storage, SMTP and worker readiness. No paid infrastructure is introduced by this code. Live inbox receipt and live Supabase object access are separate acceptance checks, not established by the test email backend.
