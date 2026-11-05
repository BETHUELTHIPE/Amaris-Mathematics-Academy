# Professional production acceptance criteria

Amaris Mathematics Academy is **pre-production** until all 20 criteria in `acceptance/criteria.json` are marked `passed`, supported by durable evidence, dated and approved by a named reviewer. A configured feature, a successful build or an unreviewed screenshot is not acceptance evidence.

The production deployment workflow executes `scripts/release/verify_acceptance.py` after the protected GitHub environment approval and before backup, migration or deployment. Any pending, partial, missing, duplicate or unevidenced criterion blocks production.

## Required evidence

| # | Acceptance condition | Pass target | Minimum evidence |
|---:|---|---|---|
| 1 | Core Web Vitals | Mobile and desktop p75: LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.10 | 28-day field report where available, plus staging lab report |
| 2 | WCAG 2.2 AA | Automated checks have no serious/critical violations and manual AA review passes | Axe/Pa11y report, keyboard and screen-reader checklist |
| 3 | Full mobile journey | Register → verify → login → browse → checkout → enrol → lesson → progress works at 360 px and 390 px | Android Chrome and iPhone Safari recordings/results |
| 4 | Resume last lesson | Re-login and Continue Learning opens the last authorised lesson at the saved position | Integration test plus staging record before/after |
| 5 | Interrupted connections | Safe drafts survive; sensitive fields are never stored; recovery action works | Offline/slow-network test on Android and iPhone |
| 6 | Useful course search | Representative grade, curriculum and topic queries return relevant courses; empty state is helpful | Approved search-query fixture results |
| 7 | Checkout states | Draft, pending, processing, paid, cancelled, failed, expired and refunded states are unambiguous | End-to-end state matrix and screenshots |
| 8 | Delayed PayFast ITN | Redirect grants nothing; delayed verified ITN activates exactly once; duplicates remain idempotent | PayFast sandbox test and database assertions |
| 9 | Student isolation | Cross-student profile, order, payment, enrolment, lesson, progress, quiz and certificate requests are denied | Permission/API suite using two students |
| 10 | Protected caching | Authenticated lessons/resources use private/no-store headers and are absent from public/CDN cache | Header tests plus unauthenticated cache probe |
| 11 | Backup restoration | Latest encrypted database and media backup restores into isolation and integrity checks pass | Restore-test log and recovery-point reference |
| 12 | Load capacity | Normal, peak, spike and degraded Locust profiles meet the agreed p95/p99 and failure-rate limits | Signed HTML/CSV reports and reconciliation check |
| 13 | Lighthouse CI | Configured mobile pages meet the repository Lighthouse thresholds | Successful GitHub Actions report |
| 14 | Critical security | Zero critical dependency, container, secret and application-security findings | pip/npm audit, Trivy, Gitleaks and reviewed security report |
| 15 | Email authentication | Verification, reset, purchase and invoice messages pass SPF, DKIM and DMARC alignment | DNS records plus message-header evidence from external inboxes |
| 16 | Safe errors | Every supported error has plain guidance, safe action, support reference and no technical disclosure | Automated response tests and staging review |
| 17 | Privacy-safe monitoring | Required failures create alerts; metric labels/logs contain no personal or payment identifiers | Alert test and label/log review |
| 18 | Essential no-JavaScript use | Navigation, registration, login, contact and checkout forms retain server-rendered fallbacks | Browser test with JavaScript disabled |
| 19 | Optional-service isolation | Flower, Prometheus, Grafana and pgAdmin can be stopped without affecting student journeys | Controlled staging outage report |
| 20 | Professional device experience | No clipping, inaccessible controls, unreadable content or broken flows on desktop, Android and iPhone | Cross-device acceptance checklist and issue closure |

## Review rules

1. Evidence must identify the tested release, environment, date and result without including passwords, tokens, personal student information or raw payment payloads.
2. Use two disposable students for permission tests and PayFast sandbox transactions only for payment tests.
3. Automated evidence must come from the protected staging workflow or an approved equivalent. Manual evidence must name the reviewer.
4. A previously passed item returns to `pending` when a relevant authentication, payment, caching, storage, email, infrastructure or user-interface change invalidates its evidence.
5. Production approval is granted only when `release_status` is changed to `accepted` in a reviewed pull request and the acceptance gate passes.

The Core Web Vitals targets follow the current Google thresholds and must be assessed at the 75th percentile on mobile and desktop. WCAG assessment targets the W3C WCAG 2.2 Level AA recommendation. Lighthouse is useful lab evidence, but field INP still requires real-user or representative interaction data.
