# Amaris site-wide responsive production gate

Status: **NOT approved for merge/deploy until PR #284 passes all required jobs**.

## Route inventory

The `frontend/e2e/sitewide_responsive.py` test enumerates every
`frontend/app/**/page.tsx` at runtime. The current branch contains **47**
distinct Next.js page files. Adding a page automatically expands the gate;
adding a dynamic route without a reviewed fixture fails the test.

- Breakpoints: 320 x 720, 390 x 844, 768 x 900, 1440 x 900.
- Runtime: production-style Nitro Node server in headless Chrome, no payment
  submissions or privileged credentials.
- For each route: no HTTP 5xx; successful public rendering or safe protected
  redirect; viewport metadata; heading; zero page-wide horizontal overflow;
  measured lab CLS <= 0.10.
- For mobile routes (390px): axe-core WCAG 2.2 AA *automated* serious/critical
  violations must be zero. Store JSON results and screenshots after any failure.
- All registered page files must be enumerated (at present, 47 x 4 = 188
  route/viewport combinations), not sampled from only Home/Courses/Contact.
- Existing strict mobile Lighthouse, Google login, tutor recruitment, AI assistant
  and student authorization checks remain mandatory and may block release.

## Sensitive flows and limitations

Never use a real customer's identity, actual PayFast payment, tutor bank details,
invoice attachment, or private course video for a site-wide *anonymous* audit.

A protected dashboard/checkout/lesson/document URL returning the login page
is **not** evidence that its authenticated contents are responsive. Accept such
a page as proof only that the anonymous guard is enforced. A separate **isolated
synthetic-account suite** must verify the signed-in experience:

1. Student: dashboard, orders, notifications, private document preview,
   active course and lesson, request-a-video ticket, course checkout and
   paid/unpaid/failed/pending states with mocked payment provider.
2. Tutor: application, verification, login, timetable CRUD, finance summary,
   slots 1-3 hours, long titles and amounts, small-screen keyboard navigation.
3. Superuser: Django Admin marketing-media CRUD, uploads, long tables and
   mobile admin forms (Django Admin is a separate backend site, not one of
   the 47 Next.js page routes).
4. Public visitors: booking timetable, registration, login, password recovery,
   matric upgrades, help, announcements and policy documents.

Tests must assert no cross-account data, no leaked payment or storage metadata,
no background POSTs, no bypassed paywall, and WCAG 2.2 AA keyboard/screen-reader
behaviour. Private flows cannot be certified merely from anonymous page redirects.

## Manual release acceptance on real devices

Test a 320px phone, a modern 390px smartphone, tablet and desktop in portrait
and landscape; 200% and 400% browser zoom where applicable, keyboard-only,
voice or screen reader, slow and interrupted connections, and long translated
or user-generated content. Validate PDF print output independently of the
horizontal scrolling *screen* preview. A green Chrome laboratory result does
not replace real-user Core Web Vitals p75 or slow-network PayFast/Zoom journeys.

### Core Web Vitals production targets

- LCP <= 2.5 seconds at p75, mobile and desktop.
- INP <= 200 milliseconds at p75 for real interactions.
- CLS <= 0.10 at p75.
- Collect actual field measurements before claiming these targets met.

## Release handling

1. Require PR #284 CI, Lighthouse and no critical failures across the complete
   route matrix, plus the independent signed-in and Django Admin acceptance.
2. Confirm a reversible Render deploy and verified previous Git SHA.
3. Promote only the validated frontend commit, without unrelated database or
   payment changes.
4. Verify live homepage, all critical public journeys, booking, login, student
   dashboard and tutor authentication at narrow and desktop widths.
5. On critical error or authorization regression, roll back Render to the
   previous healthy frontend image and recheck the live application.

**Do not claim all production flows ready until authentication-specific,
third-party payment/email and live browser acceptance have actually passed.**
