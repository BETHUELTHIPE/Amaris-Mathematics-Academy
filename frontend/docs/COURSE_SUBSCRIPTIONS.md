# Course subscription pages

## Routes and scope

- Home page: prominent navy-and-gold 4-month / 8-month comparison section.
- /subscriptions: plan comparison, next steps and frequently asked questions.
- /subscriptions/4-months and /subscriptions/8-months: course selection, plan summary and contextual enquiry form.
- Pricing page links to the subscription comparison.

The pages are subscription requests. The owner has not supplied plan prices, included course coverage, access dates or renewal terms. These details are explicitly confirmed before payment. No prices, discounts, recurring charges or access entitlements are inferred from existing one-off course prices. The existing course checkout remains separate.

## Request flow

A GET form selects a course from the existing managed catalogue, or the student chooses course guidance. Unknown course slugs show a correction message. Unsupported duration routes return not-found.

The existing contact enquiry form receives the selected duration/course in an editable message. It retains its existing validation, consent, honeypot, persistence, success/error handling and support options. Draft keys are isolated by plan and course; ordinary contact form defaults remain unchanged. A request does not activate access or collect payment.

## Verification

Added rendered plan-card, homepage semantics, unsupported duration and request-context tests in tests/course-subscriptions.test.mjs. The coding environment was unavailable during preparation; local execution and visual browser review were not performed. Run CI frontend lint, typecheck, production build, unit tests, accessibility and responsive checks before merging.

Manual acceptance:
1. Follow both homepage plan links on mobile and desktop.
2. Choose a course, update it, switch duration and confirm the selected course is preserved.
3. Choose course guidance and add a grade/module to the message.
4. Submit with consent in staging and confirm the enquiry retains the duration/course.
5. Verify required-field errors, persistence failure feedback and invalid-course correction.

Before enabling paid subscriptions, confirm total ZAR prices and course coverage, implement server-authoritative order/expiry records and independently verified gateway settlement, then validate access activation/expiry and the full payment journey in staging.
