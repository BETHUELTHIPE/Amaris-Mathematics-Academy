# Dashboard real-user Web Vitals and verified tutor acceptance

## What this measures

A small client component observes browser-reported **LCP, INP and CLS** for exact,
allowlisted student Overview, Orders, Notifications and tutor Dashboard routes only.
It samples 25% of browser page loads; exact URLs, student names, email addresses,
user IDs, payment/invoice references, cookies, tokens and detailed interaction
targets are **never transmitted or logged**. Client telemetry uses credentials=omit
and referrerPolicy=no-referrer. The same-origin endpoint rejects unknown fields,
oversized or implausible measurements, and caps the rate per running instance.

Validated events are written as single JSON summaries prefixed
`amaris_dashboard_vital` in existing Render frontend logs. No new database,
paid service, or migration was introduced. Logging is **ephemeral** and subject
to Render's log retention; avoid suggesting indefinite historical coverage.

### How to validate after a safe release

1. Inspect the Render frontend release SHA and verify that the new anonymous POST
   endpoint returns HTTP 204 for a valid synthetic test payload, 403 for a
   foreign origin, and 400 for malformed or extra fields.
2. On a non-sensitive test-only student/tutor login, inspect the browser Network
   tab: only the four allowlisted route names and the three metric names may
   be sent. Do **not** paste cookies or network HAR files.
3. Review server log lines with prefix `amaris_dashboard_vital`. Each contains
   only: `page`, `device` (mobile/desktop), `metric` and `value`.
   Zero lines is **no evidence**, not a performance pass.
4. Record counts and **p75** separately by route, device and metric, after
   collecting sufficient non-synthetic real-user observations (aim for at least
   100 reports per group; note statistical uncertainty). The frontend logs
   may be unavailable or incomplete. Low visit volume can take a long time.
5. Evaluate targets: LCP <= 2500ms, INP <= 200ms, CLS <= 0.10. LCP/CLS may
   report without interaction; **INP is not available for sessions with no
   interaction**, and browser support differs. Telemetry observations are not
   equivalent to Google's CrUX population.
6. PR #289 shipped **before** this instrumentation existed. Unless comparable
   actual *pre-change* field samples can be recovered, do not claim a quantified
   before/after real-user improvement for that specific release. This collector
   establishes a baseline for **future** changes.

## Genuine authenticated tutor acceptance

Run `.github/workflows/live-tutor-dashboard-acceptance.yml` using GitHub Actions
on release branch `render-live-current-20260918` with protected environment
`tutor-production-verification`. Create exactly these GitHub **environment
secrets** using a dedicated, verified, Django-approved tutor **test account**:

- `AMARIS_LIVE_TEST_TUTOR_EMAIL`
- `AMARIS_LIVE_TEST_TUTOR_PASSWORD`

Never use a real tutor's personal account credentials or publish them in
GitHub, issues, screenshots or chat. The read-only Playwright journey verifies
actual Supabase password authentication, Django tutor permissions, visible
timetable, stable mobile/desktop layout, and session continuity after reload.
It does **not** submit an availability slot, payment, booking or payout and
uploads no screenshot or private browser trace. Absent secrets **must block**
the test, not silently pass.

Automated contract/synthetic tests alone are **not** a successful real
authenticated tutor session. Mark live tutor acceptance complete only after a
successful protected workflow run using an approved isolated test account.
