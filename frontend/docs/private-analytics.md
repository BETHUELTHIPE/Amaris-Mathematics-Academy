# Student and tutor analytics

Student page: `/dashboard/analytics`; tutor page: `/tutor/analytics`. Both have
verified-account checks before private data is fetched. Django independently
enforces student ownership and approved Tutors-group membership. No client
role selector, arbitrary student/tutor ID, Airflow token or service-role key is
used to fetch analytics.

The shared dashboard provides:

- 7-, 30- and 90-day windows using South African dates.
- Four role-specific metric cards, line/bar timelines and a pie service mix.
- Personal-target gauges: the owner chooses the target; the app never invents
  a financial/academic goal. The arc stops at 100%, with actual over-target
  percentage and values still shown.
- A separate recorded-progress gauge. Student progress is the current average
  saved enrolment progress, independent of the period filter. Tutor completion
  counts recorded completed past paid classes, not inferred attendance.
- Accessible chart labels, keyboard-focusable data points, exact daily tables,
  reduced-motion support and private CSV export. Timeline weeks conserve all
  daily values and label the final partial week.
- Chart choices and personal goals remembered per account, role and period
  in this browser. Storage failure does not stop chart switching. Financial
  records and tokens are never written to preference storage.

Backend companion PR #434 provides schema version 1 from GET-only
`/api/v1/student/analytics/` and `/api/v1/tutor/analytics/`. It aggregates in SQL
with bounded windows instead of estimating totals from the dashboard's limited
100-order history. Financial charts use integer ZAR cents. Student spending
excludes unverified/refunded/cancelled/review orders. Tutor earnings are ledger
amounts, including held entries; payouts require provider confirmation.
Scheduled hours are explicitly distinguished from attendance. No student
identities, bank details, payment references or raw documents enter analytics.

The frontend validates role, schema, ranges, metric totals and matching series,
and strips unexpected fields. API failures render an honest unavailable state,
never sample figures or zeros labelled as live measurements. Both server API
helpers reuse the existing verified session and `cache: no-store` behavior.

`e2e/fixtures/analytics-preview.tsx` is an isolated design/test harness with
prominent sample-data disclosure. Production routes do not import it. CI
bundles the actual chart component into a temporary preview, then checks both
roles at 320, 390, 834 and 1440 pixels, chart choices, saved goals, persistence,
date selection, CSV and WCAG 2.2 AA tags. Screenshots contain only fake data.
This does not replace genuine deployed login and owner-data acceptance.

Deploy the backend endpoint before the frontend. Neither pull request enables
hosted infrastructure or changes billing. Render was billing-suspended on the
latest inspection, so staging/production acceptance remains pending. No new
database migration, paid charting provider or external analytics service is
introduced. The existing release, accessibility, security and performance
thresholds remain unchanged.
