# WCAG 2.2 AA internal acceptance review

Date: 2026-09-18  
Scope: public site, authentication, contact, courses, dashboard shell and payment-state surfaces.

This is an internal production-acceptance review, not a third-party accessibility certification.

## Automated evidence

- The responsive-browser suite runs axe-core with the WCAG 2.0/2.1/2.2 A and AA tags on the homepage, courses, contact, login and registration routes.
- Pa11y and Lighthouse accessibility gates run in CI on the production frontend build.
- The browser matrix covers Chromium, Firefox and WebKit at mobile, tablet and desktop sizes, plus named Pixel 7 and iPhone 13 profiles.
- Essential navigation and the contact form are also exercised with JavaScript disabled.

## Manual source and interaction review

| Area | Review | Result |
| --- | --- | --- |
| Keyboard focus | Shared focus-visible styling applies to links, buttons, inputs, textareas, selects and summary/menu controls. | PASS |
| Focus not obscured | Global scroll padding reserves space for the sticky header when focus/anchor scrolling occurs. | PASS |
| Target size | Primary controls are at least 48px high. Contact consent checkbox is 24px. Registration consent uses a full clickable label. | PASS |
| Form labels and errors | Required fields use explicit labels; field errors use role=alert; invalid state is exposed with aria-invalid. | PASS |
| Authentication | Login supports password managers through autocomplete=current-password; registration/reset use autocomplete=new-password; no CAPTCHA or puzzle is required. | PASS |
| OTP verification | Six 48px OTP slots have a single accessible label and numeric input mode; the flow also offers a secure email link. | PASS |
| Consistent help | Shared header/footer expose phone, email and contact/support routes throughout the public and auth experience. | PASS |
| Dragging interactions | No required drag-only interaction is used in the reviewed production journeys. | PASS |
| Status/error messaging | Success and error states use semantic status/alert roles where dynamic feedback is presented. | PASS |
| Responsive reflow | Browser E2E asserts no horizontal overflow on navigation, forms, dashboard, invoice, checkout and lesson surfaces. | PASS |
| Non-JavaScript fallback | Core navigation and contact enquiry remain operable without JavaScript. | PASS |
| Colour/focus regression | Lighthouse/axe/Pa11y remain blocking gates; visible focus uses a 3px high-contrast accent outline. | PASS |

## Review conclusion

The reviewed production journeys meet the project's WCAG 2.2 AA acceptance checks after the focus-obscuring, focus-visibility and consent-target-size hardening in this change. Any future regression detected by axe, Pa11y, Lighthouse or responsive browser tests remains release-blocking.
