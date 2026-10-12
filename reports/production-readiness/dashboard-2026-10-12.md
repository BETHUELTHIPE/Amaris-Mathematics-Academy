# Dashboard release candidate — 12 October 2026

Base: staging commit `ccc1f05943a205fbf39348f74b1ed51c7073430e`.
Candidate branch: `fix/dashboard-live-promotion`.

Staging already contains the private Orders & Payments and Notifications pages,
student-scoped backend endpoints, course invoice downloads, clickable My Courses
navigation, and responsive dashboard shell. This candidate preserves that work
and closes the remaining direct-URL and responsive gaps:

- `/orders` redirects to `/dashboard/orders`; `/notifications` redirects to
  `/dashboard/notifications`. Both destinations require a verified student.
- Dashboard page actions have a minimum 48px height.
- Long content wraps within the dashboard; course/video rows preserve their
  flex boundaries and recommendation links wrap on narrow screens.
- Unavailable course/video summary counts display a dash instead of a false zero.
- Behavioral page tests cover populated data, invoice destinations, empty/error
  states, authentication ordering, and the short URL redirects.
- The responsive browser check clicks through the navigation and checks its
  column count, 48px targets, active page, keyboard access and long-heading overflow.

## Local evidence

| Check | Result |
| --- | --- |
| Django student API, payments, live classes, video requests and invoice archive | 62/62 passed |
| Existing frontend test suite | 74/74 passed |
| New behavioral page tests | 7/7 passed |
| Dashboard/responsive contract plus new page tests | 12/12 passed |
| TypeScript | Passed |
| ESLint | No errors; two pre-existing warnings in unrelated components |
| Cloudflare/Vinext production build | Passed |
| Render Node/Nitro production build | Passed |
| OpenAPI schema validation, fail on warnings | Passed |
| Migration drift | No changes detected |
| Chromium dashboard journeys at 320, 390, 834 and 1440 pixels | 4/4 passed |
| Local Render production HTTP smoke | 6/6 redirects passed |

Production HTTP checks cover `/dashboard`, both dashboard subpages, both short
URLs and the course invoice route. Protected routes return a login redirect
with private, no-store headers; the short URLs redirect to their protected routes.

Tests used synthetic accounts/data, Python 3.12 and SQLite, and Celery's in-memory
broker. Redis was unavailable; the backend's bounded fallback cache was exercised.
No live payment, email or production student data was used. Browser tests used
installed Chromium; Firefox/WebKit downloads were blocked by network policy.
Authenticated browser checks exercise empty account states; populated data and
service errors are covered by rendered component tests and backend API tests.

## Deployment status

**Not deployed or verified live in this session.** Git read and push preflight
work through the platform's existing credentials. GitHub API requests are denied
by the environment network policy. Render API access and a Render credential are
not configured. The attempted environment draft update was rejected with
`draft_not_editable`; no configuration save or publication is claimed.

Once access is available, pass the repository's CI/staging gates, confirm the
current Render service branches and backend/frontend release alignment, promote
the exact tested commit through the release workflow, and verify the live commit,
health, authentication, private student data, invoices and responsive navigation.
Local checks do not replace those release gates or establish live readiness.
