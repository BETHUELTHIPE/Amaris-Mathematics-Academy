# Amaris real-user Core Web Vitals (RUM)

## Purpose
Observe **real browser experiences** over time, using the 75th percentile of LCP,
INP and CLS rather than the mean. No third-party analytics provider or paid
monitoring server is required.

## Privacy and collection

- 20% sampling per browser page load. The frontend sends only metric name,
  measured value, short per-navigation metric ID, a coarse allowlisted page
  category and mobile/tablet/desktop class.
- The telemetry JSON never contains full paths, query parameters, lesson IDs,
  URLs, email addresses, student identifiers, cookies, IPs or User-Agent text.
  As with any web request, transport metadata may include an IP address and
  same-origin cookies; the receiving proxy ignores them and never forwards
  them to Django or stores them in the telemetry table.
- Next.js `/api/web-vitals` is a same-origin proxy. It forwards no cookies and
  calls Django `/api/v1/web-vitals/ingest/` with a **server-only shared token**.
- Django uses an HMAC of the metric event ID for retry idempotency. Only the
  digest is persisted, never the original metric ID. The table has Supabase
  row-level security enabled and all public Data API grants revoked.
- Ingestion rejects invalid and oversize requests; per-source burst limiting
  reduces misuse. Collected samples are pruned after 90 days, opportunistically
  when new events arrive. No browser fingerprint or session recording.
- Report can be read only by active Django superusers with a Django session.
  Never expose individual rows or unaggregated reports to students/tutors.

## Release order and secret

1. Before production schema migration `content.0015_web_vitals`, confirm a
   recent **retained encrypted production PostgreSQL backup**, plus successful
   isolated restore. Existing monthly backups are not a substitute for this
   pre-migration release gate if they are stale.
2. Deploy backend with new migration first. The endpoint fails closed with 503
   until `WEB_VITALS_INGEST_TOKEN` is configured.
3. Create **one** random >=32-character token and configure its exact value as
   `WEB_VITALS_INGEST_TOKEN` on both Render production backend and Render
   live student frontend. Do not print the value or put it into GitHub source.
4. Deploy frontend and verify a synthetic telemetry POST via the **frontend's**
   same-origin `/api/web-vitals`. Verify a single row in the Django database
   (superuser view), then remove synthetic rows.
5. Validate superuser-only `/api/v1/web-vitals/report/?days=28` access,
   403 for regular staff, 204 for internal ingestion, and that student
   login/booking/payment continue to operate.
6. Only report a p75 figure after **20 valid events for that particular**
   metric/page/device group. Missing or few samples are shown as
   `insufficient_data`, not zero or a claimed passing performance result.

## Reading your p75

Login to Django Admin as a superuser, then open:
`https://amaris-production-web.onrender.com/api/v1/web-vitals/report/?days=28`

Change `days` to 7, 28 or 90. Inspect sample sizes, routes/devices and p75:
LCP <=2,500 ms, INP <=200 ms, CLS <=0.10 are the good thresholds.

**Important:** Reports are based on sampled browser events, not unique
students or real-user Chrome UX Report p75. INP may be absent for pages with
no interactions. Coverage should be assessed before drawing conclusions.

## Operational limits

- The source frontend must have `CMS_API_URL` configured to the trusted Render
  backend. The backend/forwarder must both have the same server-only secret.
- Record counts and write volume depend on student traffic; measure database
  growth after 7 days and reduce sample rate if needed.
- No real-user data can exist before the collector deploys and browsers visit.
- Production incident: disable ingestion by clearing the token on either
  service; this does not interrupt lessons, registrations or payments.
