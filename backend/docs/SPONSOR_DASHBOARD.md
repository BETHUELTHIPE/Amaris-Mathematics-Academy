# Sponsor workspace

The protected frontend route is `/sponsor`. It uses the existing Supabase login
and email verification, followed by a separate administrator-approved sponsor
account linked by the exact Auth UUID. Sponsor access does not come from an
email match, a browser parameter or user-editable metadata. The sponsor API
never creates a student profile or accepts synthetic student acceptance tokens.

## Features and data definitions

- Overview: all-time received funding, students supported, funding allocated and
  available funding. Received excludes pledges and fully refunded records.
  Allocated includes active and completed allocations; planned and cancelled
  allocations are excluded. Available funding can be negative and is labelled
  as a funding gap rather than being hidden. It is a planning total, not a
  withdrawal balance or payment account.
- Giving chart: monthly received contributions for the selected calendar year,
  with an equivalent exact-amount table. The annual goal always relates to the
  current South African calendar year, even while viewing an older report.
- Learners: sponsor-approved aliases, programme, grade/level, allocated funding
  and status. Search and status filters apply to the current page. Each API
  page returns up to 20 records; totals cover the full sponsor account.
- Progress: only the specifically linked enrollment is exposed, after explicit
  sharing permission and its timestamp are recorded. Student email, real name,
  phone, Auth UUID, documents, Zoom links and other enrollments are not returned.
- Contributions: received, pledged and refunded records remain distinct. The
  statement/report date is received_at where present, otherwise created_at.
  Received records appear in their receipt year rather than also appearing in
  the earlier pledge year. SAST is used for dates.
- CSV statements: all sponsor-owned records for the reporting year, independent
  of pagination, up to 10,000 rows. Larger exports return an explicit error
  rather than silently truncating. Formula-like references/descriptions are
  escaped. These are contribution records, not tax certificates or invoices.

## Administrator setup

1. Apply additive Django migration `0020_sponsor_dashboard` after
   `0019_student_motivation_email`. This branch builds on the earlier motivation
   email change. It also excludes sponsor accounts from that student audience.
2. In Django Admin, create a Sponsor account with the verified user's exact
   Supabase Auth UUID, name and optional organisation and annual target.
   Enable `is_active` only after checking the sponsor's identity.
3. Record genuine contributions in Sponsor contributions. Mark funding Received
   only after independent receipt verification and enter its receipt timestamp.
   A pledge is not received money. This release does not add a payment gateway,
   debit a sponsor or automatically reconcile bank transfers.
4. Create Sponsor allocations for the relevant students, using authorised
   sponsor-visible aliases. Specify programme, level, amount, dates and status.
   To share course progress, link the same student's enrollment and record
   permission before enabling Share progress. Django Admin validates both.
5. Deploy the backend and frontend revisions together and verify the environment's
   CMS_API_URL. The frontend uses the existing secure server-side access token;
   it never sends a service-role key to a browser. The sponsor portal is linked
   from the existing dashboard navigation.

All three new tables enable RLS and revoke public/anon/authenticated Data API
access. Django serves records after identity and account-ownership checks.
Dashboard, statement and frontend page responses are private/no-store. Sponsor
APIs are read-only; financial updates remain in permission-controlled Admin.

## Verification and release limits

Local tests cover approval, verification, UUID binding, cross-sponsor isolation,
student data minimisation, explicit progress consent, inconsistent enrollment
protection, exact financial totals, distinct student counts, year selection,
pagination, full-year exports, formula injection and database constraints/RLS.
Rendered React tests cover populated, empty, approval and unavailable states,
escaped aliases, unknown progress, statement links, pagination and preview labels.
The professional responsive layout includes mobile navigation, a scrollable
contribution table, keyboard controls, reduced-motion styles and print styling.

The private design preview contains fictional sample records only. It is not
connected to the live student database. The preview requires the owner's
ChatGPT sign-in. Browser visual and interactive acceptance remains outstanding:
local Chromium could not start because Unix sockets are restricted, the cloud
browser could not reach the local preview server, and the private hosted preview
showed its sign-in gate. Do not mark accessibility or mobile browser gates PASS
based on build/render tests alone.

Production and staging Render services were still suspended for billing during
this task. No production data, live payments or access grants were changed.
Before live rollout, restore existing services, complete CI, apply the migrations
in isolated staging and verify two synthetic sponsors, a normal student denied
access, consent-hidden progress, CSV download and mobile/desktop navigation.

Local verification on 11 November 2026: the integrated backend suite completed
285 tests, with 282 passed and three Redis-dependent integration checks skipped.
The 11 sponsor tests passed again after the reporting-date refinement. All 82
frontend tests passed, including eight rendered sponsor-dashboard tests. Frontend
production build and TypeScript checks passed. Backend Ruff, Black, Mypy,
migration-drift and OpenAPI validation passed. Frontend ESLint reported no errors
and two existing warnings in unrelated files. Local Python/PostgreSQL were
3.12/16.2; repository CI targets 3.13/17. No visual/browser acceptance claim is
made from these results.
