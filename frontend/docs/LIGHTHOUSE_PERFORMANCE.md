# Lighthouse Performance Gate

The release candidate is accepted by the strict Lighthouse profile only when every audited public route displays a **100/100 Performance** score from the generated Lighthouse JSON report.

Audited routes:

- `/`
- `/courses`
- `/contact`

The strict desktop profile runs each route three times against the production-like preview server. The verifier also enforces FCP, LCP, CLS, TBT, and Speed Index budgets and writes `score-summary.md` into the Lighthouse artifact. A separate mobile profile remains enabled so a perfect desktop lab score cannot hide a mobile regression.

A report is never marked PASS by changing a label or bypassing an audit. The score must come from a completed Lighthouse run.
