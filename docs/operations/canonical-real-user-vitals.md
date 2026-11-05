# Amaris real-user experience: canonical reporting contract

**Status:** release-gated, production persistent collection disabled until acceptance is verified.

## Sampling and privacy (one pipeline, never double-count)
- Existing Render-log diagnostics sample **25%** of eligible exact public/dashboard routes while the new persistent collector is disabled.
- When all three release flags are intentionally enabled (client `NEXT_PUBLIC_ENABLE_WEB_VITALS=true`, Next server `RUM_FORWARD_ENABLED=true`, Django `RUM_PERSIST_ENABLED=true`), only the new **20%** first-party sampled pipeline is active; the old 25% log path is skipped.
- The browser's Next `useReportWebVitals` produces authentic LCP/INP/CLS values. A single randomly sampled browser runtime is eligible per navigation; the test harness can force sample eligibility but may **not** fabricate measured values.
- Honor DNT and Global Privacy Control. Only broad allowlisted route groups (home, courses, contact, announcements, matric, booking, student overview, tutor dashboard), mobile/tablet/desktop tier, effective network class, metric and numeric value may leave the browser.
- Never transmit IDs, account references, full paths, query strings, referrer URLs, cookies, auth headers, metric entries/targets or payment information. Only the server-to-server Next request attaches the private shared ingestion token and a trusted 12-hex frontend release. Do not put the token in NEXT_PUBLIC or expose its value.
- The Next route rejects foreign origins, unknown fields, oversized payloads, out-of-range/invalid measurements, and missing/short secrets. Django rejects unauthenticated requests, invalid release tags and writes while `RUM_PERSIST_ENABLED=false`.
- Reporting is best effort. It must never affect lessons, checkout, login, tutor schedules, or student navigation.

## Data model and interpretable reports
- Store daily **counts only** in fixed buckets keyed by UTC day, **frontend release**, coarse route group, device, coarse network, metric and bucket. No raw browser observation or client identity is persisted.
- Superuser-only Django Admin report: `/admin/content/webvitalbucket/report/` shows rolling 28-day p75 and separate seven-day week cohorts. No staff or student access.
- Approximate p75 is the **upper edge** of the bucket containing the 75th percentile rank. An open-ended bucket is displayed as *above measurement range*, never as a precise point estimate.
- Suppress any group with **fewer than 20 observations**. For 20–99 observations, treat the histogram p75 as preliminary; aim for at least 100 real-world samples per comparison cohort when assessing releases.
- Targets: LCP <= 2,500 ms; INP <= 200 ms; CLS <= 0.10. Not every navigation emits INP; absent observations are unknown, not zero.
- Daily counts older than 90 days are pruned opportunistically; this is not an indefinite data warehouse. Sample fractions mean cohort sample counts are not equivalent to total traffic.

## Required verified acceptance
1. All Django formatting, migration, auth and privacy tests pass in the backend PR.
2. A genuine end-to-end test in an **isolated SQLite Django database** and production-equivalent Nitro/Chrome build proves browser-generated LCP -> same-origin Next API HTTP 204 -> HTTPS token-authenticated Django -> daily histogram -> authenticated superuser p75 row after >=20 real browser emissions. Verify opt-outs and cleanup.
3. Separately run staging deployment behind protected staging tokens and verify no account, payment or unknown payloads are stored.
4. Only after these pass, take and verify a **fresh retained encrypted production backup** before applying migration 0015. Deploy backend first with persistence OFF; verify migrations, superuser report and 403/400 privacy rejection. Then deploy frontend with emission OFF, bind matching private secrets, and enable both server switches and browser sampling during a controlled rollout. No paid infrastructure required.
5. Observe real visitors; do not label CI synthetic samples as field evidence. Never manufacture a pre-change p75 for a release that predates sampling. Preserve release cohort names for valid future comparison.

## Independent source-of-truth
- Canonical persistent frontend candidate: PR #296, replacing older overlapping RUM PRs #271, #283, #286 and stale PR #294.
- Canonical backend aggregator: PR #282, superseding PR #270.
- Pre-release tests must not mutate production PostgreSQL or activate persistent production ingestion.
