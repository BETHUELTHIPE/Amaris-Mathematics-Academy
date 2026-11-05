# Responsive and browser E2E coverage

This suite uses Playwright for Python and runs the same representative UI checks in Chromium, Firefox, and WebKit at three viewport sizes:

- mobile: 390 × 844
- tablet: 834 × 1112
- desktop: 1440 × 1000

Covered real application surfaces:

- primary navigation, including the compact mobile/tablet menu
- contact/enquiry form layout and safe field interaction without submission
- authenticated student dashboard using a development-only synthetic student adapter
- invoice table and document preview layout
- course enrolment / secure PayFast checkout entry UI and payment-pending recovery state
- course structure that currently represents the lesson-delivery entry surface

## Important scope boundary

The repository does not currently contain a dedicated checkout page that posts a transaction to PayFast, and it does not currently contain a dedicated lesson-player route. The browser suite therefore does not claim end-to-end checkout completion or lesson-player coverage. It tests the real checkout entry/payment-state surfaces and current course/lesson structure only.

The synthetic student adapter is accepted only when both `NODE_ENV=development` and `E2E_SYNTHETIC_STUDENT=true`. It is unavailable in production mode.

No real payments, emails, SMS, WhatsApp messages, Zoom calls, AI requests, or external video API requests are made by this suite.
