# Sponsorship on the Render student website

Student site: https://amaris-mathematics-academy-live-students.onrender.com
Django backend: https://amaris-production-web.onrender.com

The footer links to `/sponsors`. Sponsorship testing is separate from course payments and creates no enrollments or payment records.

Set `SITE_URL` to the student site origin and `CMS_API_URL` to the backend `/api/v1` URL. Set `PAYFAST_SPONSOR_MODE=sandbox` on the frontend. The default merchant is PayFast’s public shared sandbox account. To use a personal sandbox merchant, configure `PAYFAST_SPONSOR_SANDBOX_MERCHANT_ID`, `PAYFAST_SPONSOR_SANDBOX_MERCHANT_KEY` and `PAYFAST_SPONSOR_SANDBOX_PASSPHRASE` together on the server. Never mix a personal passphrase with the shared merchant. No real money is charged.

The form validates amounts from R5 to R100,000, then signs a sandbox request on the server. Return/cancel pages do not confirm payment. Test transactions are viewed in PayFast’s sandbox dashboard; this development flow does not process ITNs or issue receipts.

For a future live hosted-link integration, set `PAYFAST_SPONSOR_MODE=live` and the owner’s public `PAYFAST_SPONSOR_URL`. The sandbox checkout is disabled in live mode.

Render builds with `vite build --config vite.node.config.ts` and runs `.output/server/index.mjs`. It does not use the Sites publishing script.
