# Tutor recruitment frontend

`/tutor/apply` is the public recruitment page and authenticated application/status page. Navigation includes **Become a tutor**. Applicants can use an existing Amaris account or `/tutor/register`, verify their email at `/tutor/verify-email`, and sign in at `/tutor/apply/login`. Google OAuth callbacks and email verification return to the application instead of the student dashboard. Approved tutor portal access remains separate.

The form collects contact details, academic qualifications, institution, subjects, programme(s), grade/module levels, experience, **one to twelve future teaching date/start-time slots with 1–24 whole teaching hours each in South African Standard Time (UTC+02:00)**, and motivation, plus qualification uploads. The native date/time controls support evenings, weekends and multiple proposed sessions. The client and same-origin BFF both validate calendar dates, future times, half-hour starts, overlapping sessions and duration. The server derives the persisted `availability` summary from chosen slots, ignoring forged free-text availability. Django stores this in its existing private `TutorApplication.availability` field (no migration) and the applicant cannot publish bookable times until tutor approval. It includes a recruitment privacy notice and declaration. Files are not saved to browser storage. On submission errors the enhanced form retains entered values and selected files; a lost response can be retried without creating another application. A native multipart HTML form also works without JavaScript.

The same-origin BFF validates the authoritative Supabase user before forwarding a server-held bearer token. It bounds request bodies (including streamed requests without Content-Length), forwards multipart file bytes, and returns private/no-store responses. Applicant documents are downloaded through an authenticated proxy with attachment/nosniff/sandbox headers. No service-role keys or raw storage URLs are exposed.

After submission the page shows the server-generated reference and review status. Email is shown as sent only after the backend accepts the acknowledgement; pending delivery offers a rate/backoff-limited retry. The application does not approve the applicant or grant any tutor permissions.

## Dependency and release

Requires backend recruitment PR #197, commit `1e5d308ae897cf91f3a36d14ae0fa858fd892e6f`, before deploying this frontend. The backend owns private file validation/storage, database identity binding, recruitment permissions and email delivery. The GitHub browser workflow pins this backend contract to make combined testing reproducible. It uses synthetic local Auth and captured file mail, not production credentials or an external inbox.

The backend and frontend production histories differ. This PR targets `render-live-current-20260918`; the backend targets `production-release-20260923`. Do not overwrite one with the other. Production release requires the matching approved backend, green exact-head CI, staging verification and a controlled live Supabase/SMTP acceptance test. This implementation has not been deployed.

## Verification

- Frontend: `npm ci --include=dev`, `npm run typecheck`, `npm run lint`, `npm run test:unit`, `npm run build`.
- Render runtime: install the exact Nitro/Tailwind versions used in `.github/workflows/tutor-recruitment-acceptance.yml`, then `NODE_ENV=production NITRO_PRESET=node npx vite build --config vite.node.config.ts`.
- Paired browser: install `frontend/e2e/requirements.txt` and backend requirements; set `TUTOR_BACKEND_ROOT` to the matching backend directory and optionally `TUTOR_CHROME_PATH` to an installed Chrome binary; run `python frontend/e2e/tutor_recruitment.py`.
- The harness tests registration, code verification, a fresh login session, form submission, private upload/download, receipt and captured acknowledgement. It audits page overflow and Axe accessibility across narrow mobile, mobile, tablet and desktop sizes.
- Tests use temporary SQLite, private local files, a fake Auth service and captured mail. They do not prove live Supabase signup or SMTP inbox delivery.
