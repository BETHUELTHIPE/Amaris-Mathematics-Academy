# Curriculum course subscriptions

The paired frontend change targets `render-live-current-20260918`; this backend
change targets `production-release-20260923`. Do not merge one entire deployment
branch into the other. No production service, database or payment was changed
while implementing this feature.

## Product rules

| Term | Upfront total | Curriculum choice |
| --- | --- | --- |
| 4 calendar months | R3,800.00 | One required curriculum |
| 8 calendar months | R7,600.00 | One required curriculum |

Both are fixed-term purchases, without automatic renewal. Prices are the same
for CAPS, IEB, TVET NATED, TVET NC(V), and University / UNISA. Access covers
published courses in the selected curriculum, including courses published later
during the term. Live classes, Zoom bookings and custom video requests remain
separate purchases. A separately purchased course retains its existing access.

The existing course curriculum strings map as follows (case-insensitive):

| Subscription | Course curriculum values |
| --- | --- |
| caps | CAPS |
| ieb | IEB |
| nated | NATED, TVET NATED |
| ncv | NCV, NC(V), TVET NC(V) |
| university | Higher Education, University, UNISA, University / UNISA |

## Payment and access

`COURSE_SUBSCRIPTIONS_ENABLED` defaults to false. Enable only in an isolated
sandbox staging environment initially. The existing PayFast settings and
`PUBLIC_SITE_URL` / `PUBLIC_API_URL` must point to the intended HTTPS environment.
Checkout calculates the price on the server and signs the PayFast form. Browser
return parameters cannot activate access. Only independently verified ITNs with
matching merchant, amount, student, product and gateway mode start the term.
Calendar-month expiry is checked on courses, lessons, progress and resume.
Duplicate successful notifications do not extend the term. Verified refunds or
reversals revoke subscription access. Sandbox records cannot grant live access.

The private student API is `/api/v1/student/subscriptions/`, with `checkout/`,
`<reference>/`, and `<reference>/invoice/` endpoints. Students can view only their
own records. Invoices reuse the existing PDF letterhead renderer and
`student_private` storage; PDFs are delivered through authenticated requests.
No new receipt email delivery or second payment provider is implemented.

## Integration and release

1. Review the paired frontend and backend PRs and their checks. Migration
   `0022_curriculum_subscriptions` branches from production migration `0018`.
   Pending PRs #438/#439 introduce other migration leaves: if integrated together,
   add a merge migration after inspecting the final migration graph. Do not
   silently depend on unmerged work or renumber an applied migration.
2. Apply the migration to an isolated staging PostgreSQL database, verify RLS and
   revoked browser-role grants on `content_curriculumsubscription`, and confirm
   that Django's service role can access the table. The nullable enrollment FK
   leaves existing direct purchases unchanged.
3. Deploy both reviewed commits to staging. Enable subscription checkout there
   with PayFast sandbox credentials. Verify every curriculum/term price; an
   authenticated, email-verified student must choose a curriculum.
4. Complete a real sandbox gateway round trip, then verify ITN, private status,
   invoice download, matching curriculum lessons and progress. Check another
   student's denial, duplicate callback, expiry, reversal, retained direct course
   purchase access, and a course published after subscription activation. Check
   stale pending orders and overlapping purchases with the gateway before launch.
5. After production authorization and protected checks, take the required backup,
   deploy the backend migration/code before the frontend, and enable live
   checkout only after gateway acceptance. Confirm exact deployed SHAs, readiness
   and a controlled production smoke. Never manufacture a paid record for a test.

To pause new sales, set `COURSE_SUBSCRIPTIONS_ENABLED=false`; existing paid access
continues through its term. For a code rollback, disable checkout first and retain
the additive schema and payment records. Do not drop financial records or reverse
the migration after purchases without a reviewed recovery plan.
