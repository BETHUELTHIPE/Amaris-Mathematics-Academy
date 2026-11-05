# Amaris Mathematics Academy

Online mathematics course platform for South African school, TVET, college and university students.

## Repository structure

The project is deliberately split into two application folders so frontend and backend work stay separate and easy to maintain:

```text
Amaris-Mathematics-Academy/
├── frontend/              # Web UI, frontend code, assets, tests and frontend scripts
├── backend/               # Django API/CMS, Celery, data services, Docker and monitoring
├── .github/               # GitHub Actions and dependency automation
├── acceptance/            # Shared production-acceptance evidence configuration
├── docs/                  # Shared architecture, CI/CD and performance documentation
└── scripts/release/       # Shared deployment, health-check and rollback automation
```

Frontend-specific tools and code must stay in `frontend/`. Backend-specific tools and code must stay in `backend/`. Only repository-wide CI, documentation, acceptance and release automation belongs at the root.

## Current features

- Public course catalogue, pricing, academy information and enquiry form
- Supabase email-and-password registration and login
- Mandatory email verification before dashboard or course enrolment access
- Six-digit verification-code screen plus secure email-link callback
- Forgot-password and secure password-update flows
- Private student dashboards and student-owned Supabase profile records
- Row Level Security policies that restrict each profile to its authenticated owner
- Cloudflare D1 support for course progress and contact enquiries
- Branded student documents, letterhead and invoice previews
- Django CMS with a branded Jazzmin administration dashboard
- Admin-managed courses, modules, lessons, videos, resources, pages, pricing and enquiries

## Technology

### Frontend

- Next.js 16, React 19 and Vinext
- TypeScript and Tailwind CSS
- Supabase Auth and PostgreSQL
- Cloudflare Workers, D1 and Sites hosting
- Vite, Lighthouse, Pa11y and Playwright browser testing

### Backend

- Django 5.2, Django REST Framework and Jazzmin
- Gunicorn with Uvicorn workers
- PostgreSQL, Redis and Celery
- NGINX and Docker
- Prometheus, Grafana, Flower and cAdvisor
- Encrypted backup and restoration tooling

## Frontend environment

Copy `frontend/.env.example` to `frontend/.env.local` and set:

```env
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_your_key
SITE_URL=https://your-site.example.com
CMS_API_URL=https://your-cms.example.com/api/v1
```

Never commit a Supabase secret or service-role key. The website uses only a publishable key, with database access controlled by Row Level Security.

## Supabase setup

Apply the SQL files in `frontend/supabase/migrations/` in timestamp order. In Supabase Auth:

1. Enable email and password authentication.
2. Keep email confirmation required.
3. Add the production site URL and `/auth/confirm` callback to the redirect allow list.
4. Configure custom SMTP for delivery to external student email addresses.
5. Use `{{ .Token }}` in the confirmation email template when six-digit codes are required. The secure confirmation link is also supported.

## Frontend development

```bash
cd frontend
npm ci
npm run build
```

Other frontend quality commands are documented in [`frontend/README.md`](frontend/README.md). The production bundle targets Cloudflare Workers.

## Backend development

The Django administration/API service is in [`backend/`](backend/). Its setup and deployment instructions are in [`backend/README.md`](backend/README.md). The public website falls back to its bundled content until `CMS_API_URL` points to a deployed HTTPS Django service.

The backend disaster-recovery policy and operator runbook are in [`backend/docs/DISASTER_RECOVERY.md`](backend/docs/DISASTER_RECOVERY.md). Monitoring remains observational: Prometheus, Grafana, Flower, exporters or pgAdmin can fail without stopping the student platform.

## Error recovery

The public site includes branded recovery routes for HTTP 400, 403, 404, 429, 500, 502 and 503 responses, plus payment pending, payment cancelled, payment failed, expired sessions and lost connections. Automatic 404 and application-error boundaries use the same dependency-light design. Every recovery response carries an opaque `X-Correlation-ID` and displays a copyable support reference without exposing a stack trace or infrastructure detail.

Registration and enquiry drafts use short-lived `sessionStorage` entries in the current tab. Only explicitly allowed text and select fields are retained. Passwords, OTPs, tokens, consent controls, payment fields and uploads are excluded and successful submissions clear their drafts.

## Load and capacity testing

The staging-only Locust suite is kept under `backend/load_tests/`. It covers public course discovery, account entry points, authenticated learning, progress, application checkout creation and payment-status polling. Direct PayFast traffic and the live Amaris hostname are blocked by default. See [`backend/load_tests/README.md`](backend/load_tests/README.md) and [`backend/load_tests/CAPACITY.md`](backend/load_tests/CAPACITY.md).

## Performance

Frontend performance tooling and browser evidence live with the frontend. Backend performance, database, Redis, Celery and infrastructure tuning live with the backend. Shared performance policy and targets remain in [`docs/PERFORMANCE.md`](docs/PERFORMANCE.md).

## Quality gates and releases

GitHub Actions remains at repository level in `.github/` and runs frontend commands from `frontend/` and backend commands from `backend/`. Successful `main` builds promote an immutable backend image to staging; production requires the configured approval and release safeguards. See [`docs/CI_CD.md`](docs/CI_CD.md).

Amaris remains **pre-production** until every professional acceptance criterion has approved evidence. See [`docs/ACCEPTANCE_CRITERIA.md`](docs/ACCEPTANCE_CRITERIA.md).
