# Academy announcements

Public route: `/announcements`. The page uses the existing public Django
`/api/v1/announcements/` endpoint through `CMS_API_URL`; no database migration is
needed. Header, mobile navigation and footer all receive the new link while
retaining existing pages.

## Publishing

In Django Admin → Content → Announcements, add a title and plain-text message.
Optionally add a link label and a relative site path (for example `/courses`) or
an HTTPS URL. Set a positive priority to include the notice in Priority notices.
The highest-priority notice appears in the featured card; equally prioritized
notices use newest ID first. Drafts and future scheduled publications are
excluded by the existing backend.

Set `is_published` when ready, and optionally set `publish_at` and `expires_at`.
Expiry means the notice stops appearing; the displayed time is South African
time. It is not presented as an event date or registration deadline. CMS reads
use the existing 60-second revalidation policy; backend caching may also apply.
To remove a notice, unpublish it. Never publish personal student/payment data.

The page distinguishes a published empty feed from an unavailable service,
offers a retry link, and does not substitute invented announcements. Search and
priority filters use ordinary GET requests and remain usable without JavaScript.
Messages are escaped text, not HTML. Unsafe link protocols, protocol-relative
URLs and credentialed links are suppressed.

## Verification

Run `npm ci --include=dev`, `npm run typecheck`, `npm run lint`, and `npm test`
in `frontend/`. The restored page passed all 96 frontend tests on 15 October
2026; TypeScript and the standard production build passed. Lint had zero errors
and two pre-existing warnings. The original implementation was also tested in
Chromium; the restored candidate must pass its own exact-head browser CI.

The Announcements acceptance workflow runs the actual Render build and a local
synthetic CMS/browser harness. It checks populated, empty and unavailable feeds;
expiry and unsafe links; search and filtering without JavaScript; overflow at
320/390/834/1440 widths; page-main Axe WCAG A/AA tags; keyboard focus and page
errors. It preserves desktop/mobile screenshots. This automated check is not a
full manual accessibility audit or live CMS verification.

Run the isolated browser harness locally with test-only build tools:

```sh
npm install --no-save --package-lock=false nitro@3.0.260903-beta @tailwindcss/vite@4.3.3 playwright@1.62.0
NODE_ENV=production NITRO_PRESET=node npx vite build --config vite.node.config.ts
npx playwright install chromium
node e2e/announcements.mjs
```

The harness starts its own synthetic CMS and production frontend on local ports
4312 and 4320–4322. It saves screenshots under `/tmp/amaris-announcements` by
default. Optional overrides: `ANNOUNCEMENTS_ARTIFACTS`,
`ANNOUNCEMENTS_CHROME_PATH`, `ANNOUNCEMENTS_PLAYWRIGHT_MODULE`. Restricted local
environments can set `ANNOUNCEMENTS_SINGLE_PROCESS=true` with a headless-shell
binary; this does not alter the deployed application.

This frontend-only change publishes no actual notices and changes no production
data, database schema or services. Release through the existing release process.
Rollback restores the previous frontend SHA; no database rollback is involved.
