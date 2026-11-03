# Production acceptance — authentication, PayFast, invoices and field Web Vitals

Updated: 20 October 2026. This is an **evidence record**, not a claim of production certification.

## Existing production state

The Render student frontend runs a live release, and the latest public browser/auth/assistant smoke checks passed. Public 200/401/403 status checks **do not** prove an authenticated human tutor/admin session, real payment receipt, Gmail delivery or actual user Core Web Vitals.

## Executed controls

| Boundary | Evidence | Result / caveat |
|---|---|---|
| Real Django session/role authorization, tutor ownership, finance and superuser marketing/monitoring | [PR #285](https://github.com/BETHUELTHIPE/Amaris-Mathematics-Academy/pull/285) / Actions `39415007755` | PASSED on isolated PostgreSQL 17 with synthetic accounts; production login not tested |
| PayFast actual sandbox **hosted-wallet** (courses, classes, video requests) | [PR #240](https://github.com/BETHUELTHIPE/Amaris-Mathematics-Academy/pull/240) / Actions `38992048182` latest rerun | FAILED: course completed; one 1-hour class rejected by sandbox and two further browser actions timed out; 6/6 and 3/3 acceptance **not** established |
| Provider-issued ITN and Django receipt with PDF | [PR #245](https://github.com/BETHUELTHIPE/Amaris-Mathematics-Academy/pull/245) / Actions `38999735460` | PASSED on isolated HTTPS Django instance; not production provider callback or SMTP-to-Gmail |
| Gmail inbox attachment | Gmail search, 17 Oct 2026 | A self-sent test PDF exists; not correlated to provider payment/Django SMTP; FAILS final delivery evidence |
| Real-user LCP/INP/CLS | Draft backend [PR #282](https://github.com/BETHUELTHIPE/Amaris-Mathematics-Academy/pull/282), frontend [PR #286](https://github.com/BETHUELTHIPE/Amaris-Mathematics-Academy/pull/286) | NOT LIVE; do not invent field p75 or treat Lighthouse as RUM |

## Required staging-to-production acceptance

1. **No live-money payments for tests.** Create a disposable student, tutor, slot and purchase with unambiguous unique references on isolated staging. Use PayFast's genuine sandbox hosted checkout and only its test funds.
2. Confirm provider success from a signed, PayFast-issued **server-to-server ITN** delivered to the staging HTTPS callback. Verify signature, merchant, amount, reference, provider validation and replay protection. A browser success page alone never fulfils.
3. Verify a **single** paid booking/course/video request, a matching invoice number, payment receipt PDF bytes and SHA256 private-storage archive, and tutor earnings ledger without exposing student identity. A held tutor earning is not proof of a bank transfer.
4. Dispatch via **staging Django external SMTP**, then read the matching recipient Gmail email and check sender, invoice reference, PDF attachment and receipt timestamps. A local Django outbox or a self-sent Gmail PDF is insufficient.
5. Using real **authenticated staging browser sessions**, test a registered tutor can only see/update their own slots, read only their own aggregate earnings and never view another student's identity; check anonymous/staff 401/403.
6. Using staging **superuser browser session**, test marketing PDF/image/video CRUD and admin monitoring/report access, and verify ordinary staff cannot create/change/delete protected marketing content. Do not use a production superuser password in CI.
7. Promote guarded code backend-first only after branch CI and staging proof; keep backups and rollback. Revalidate the same live read-only paths after deployment. Do not create real charges or bank payouts without explicit transactional approval.

## Field Web Vitals release gate

- Collect from the browser using `web-vitals` only after private ingest token exists on both backend and frontend, privacy policy is published, Supabase aggregate-table RLS is verified and staging beacon POST returns 204.
- Broad anonymous route category, device-size class and coarse network only; **never** store full URLs, IPs, account IDs, event or payment data. Respect DNT / GPC.
- Report only when each cohort has at least 20 genuine samples, over rolling 28 days. The p75 is an **upper bound** of a histogram bin, not exact CrUX p75.
- Targets: LCP <= 2.5s; INP <= 200ms; CLS <= 0.10. A newly deployed collector cannot immediately prove these thresholds.
- Do not fabricate synthetic production measurements or set up paid telemetry without prior cost approval.

**Current gate:** CI authorization PASS; full three-service PayFast hosted-wallet FAIL; external staging SMTP-to-inbox NOT VERIFIED; field p75 NOT AVAILABLE. Do not mark all four end-to-end controls accepted.
