# Matric Upgrades page

Route: `/matric-upgrades` on https://amaris-mathematics-academy-live-students.onrender.com.

This carries the working-adult/shift-worker page from PR #209 to the current Render release branch and incorporates the confirmed brief: adults and anyone upgrading matric are the main audience, and securing an authorised exam centre is required before attending Amaris classes. It adds the page to shared desktop/mobile/footer navigation while preserving the existing announcements, tutor and student features.

Content covers the four-step exam-registration and tuition journey, day/night shifts, family responsibilities, subject enquiries and progression towards further study. Fees, places and class availability are not invented. Official examination registration and certification remain separate from academy tuition.

Calls to action use the existing `/register`, `/book-online-live-class` and `/contact` routes. External exam guidance links open in a new tab with `noopener noreferrer`. No database, account or payment changes are required.

The earlier draft passed Quality Gates and Release and Live Staging Acceptance CI. Validate the current release with TypeScript, the navigation test, the Render/Nitro production build and a local production browser preview, including responsive layouts and accessibility.
