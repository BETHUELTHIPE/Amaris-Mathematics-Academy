# Curriculum subscription pages

The homepage now links to `/subscriptions/4-months` (R3,800) and
`/subscriptions/8-months` (R7,600). `/subscriptions` compares the plans. Each
detail page requires one explicit curriculum selection: CAPS, IEB, TVET NATED,
TVET NC(V), or University / UNISA. No curriculum is preselected.

Both plans include one hour of live tutor support per week, delivered as two
30-minute Zoom sessions, plus published courses in the selected curriculum. The
first session focuses on understanding; the second on application and revision.
R950/month is an equivalent comparison, not a monthly billing instruction. The
upfront totals remain R3,800 and R7,600. No guaranteed grade, invented discount,
or fixed 16-/32-week session count is advertised for a calendar-month term.

After verified payment, an active subscription links to Contact so the student
can arrange the included sessions with the academy using their reference. These
included sessions must not be sent through the separately charged hourly
checkout. This release does not add an automatic subscription slot allocator.
Verify the academy's scheduling and attendance process in staging before enabling
sales; additional tutoring and custom video requests remain separate purchases.

The choice and term survive the verified sign-in redirect. Checkout displays the
selected curriculum and fixed upfront total, using signed fields from Django's
student subscription API. There is no automatic renewal. Browser return URLs
read the private server payment record; they cannot grant course access.
`/dashboard/subscriptions` shows the student's subscriptions and private invoice
downloads. Status, checkout and invoice responses use private no-store headers.

This change targets the actual frontend branch `render-live-current-20260918`.
It requires the paired backend change on `production-release-20260923`; do not
merge those entire branches together. The backend launch flag defaults off until
staging payment acceptance. Its `docs/curriculum-subscriptions.md` contains the
migration, storage, entitlement, sandbox acceptance and rollout checklist.

Validation includes TypeScript, scoped ESLint, subscription contract tests and a
production Node build. The isolated GitHub browser workflow checks homepage
prices, required single curriculum selection, mobile/desktop overflow, WCAG axe
checks and sign-in continuation, and uploads a screenshot. Run it before launch.
The browser harness intentionally accepts only a local preview URL and never
submits a payment. A real sandbox gateway round trip is a separate release gate.
