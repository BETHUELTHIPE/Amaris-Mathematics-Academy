# Anonymous real-user Core Web Vitals (RUM)

## Design and consent safeguards

Browser measurement uses Google's small `web-vitals` standard build (`onLCP`, `onINP`, `onCLS`) on a **20% random sample** of navigations after initial paint. It respects browser Do Not Track and Global Privacy Control flags.

Only these fields are transmitted: metric name, measured numeric value, an **allowlisted broad page group**, device-size class, and coarse `navigator.connection.effectiveType` ("3g", "4g", etc.). The device/network groups describe estimates, not real physical cell networks. Student-specific paths, checkout, profile, orders, payment, auth screens, query strings, IP addresses, account identifiers and metric navigation IDs are not transmitted.

The frontend uses a same-origin API route `/api/field-vitals`; it removes unknown fields before forwarding to Django's `/api/v1/rum/` through a **server-only shared token**. No token reaches the browser. The production Django database stores **daily histogram counters only**, not individual visitor events. Supabase RLS and privilege revocations block the public Data API. A light opportunistic pruning routine deletes aggregate rows older than 90 days.

A read-only report is available at `/admin/content/webvitalbucket/report/` to superusers only. It shows conservative **p75 histogram upper bounds** over 28 days and suppresses any cohort with fewer than 20 observations. Do not mistake histogram upper bounds for an exact p75 or for a Google CrUX field percentile.

## One-time staging configuration before release

Generate one strong random token in your secrets manager; **never commit or paste it into issues**.

Set the same `RUM_INGEST_TOKEN` on both the **staging Django backend** and its **staging frontend**, then set `NEXT_PUBLIC_ENABLE_WEB_VITALS=true` on the staging frontend and confirm `CMS_API_URL` points to that isolated staging backend `/api/v1` endpoint.

Important: the default is **disabled** on the client. Without both server secrets, ingestion fails closed. The frontend must be rebuilt after enabling `NEXT_PUBLIC_ENABLE_WEB_VITALS`.

## Release and verification

1. Verify `content.0015_web_vital_bucket` is compatible with the production migration history and inspect the genuine, retained encrypted production backup before migration.
2. Run backend Django migration/permission/security tests in CI and deploy **backend first** to staging, with the staging migration applied only there.
3. Deploy staging frontend, exercise a real Chrome navigation and an interaction (INP cannot be observed for a visit without interaction). Verify Django receives a 204 from `POST /api/v1/rum/` using the private server route. Make sure 401/403, malformed payloads and rate limiting fail closed.
4. Verify no raw URLs or visitor data are persisted and that the table has RLS enabled. Verify the superuser report with `\u2265 20` samples; do not generate synthetic production visitor events.
5. Promote to production only with all release gates green, and confirm both service health endpoints before and after.
6. After 28 days, review p75 estimates split by public-page group, mobile/desktop and effective network class. For mobile focus on 3g/slow cohorts **only when 20+ measurements exist**.

Recommended targets: **LCP \u2264 2,500 ms**, **INP \u2264 200 ms**, **CLS \u2264 0.10** at p75. The report is intentionally empty until there is enough real traffic. No synthetic values or zeroes are to be inserted into production.

## Operations

- Metrics are sampled and may be biased by low-traffic days, browser API support, traffic composition, or privacy settings. A missing INP sample is not a zero-latency interaction.
- The data reflects field Web Vitals from participating browsers; Lighthouse scores measure controlled lab performance and are not interchangeable with field p75.
- No paid analytics provider, tracking pixels or third-party cookies are involved.
- Database writes are bounded to three histogram increments per sampled page. If real-traffic volume rises, revisit rate limiting and transaction throughput.
