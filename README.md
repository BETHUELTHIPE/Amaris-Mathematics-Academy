# Amaris Mathematics Academy

Online mathematics course platform for South African school, TVET, college and university students.

## Current features

- Public course catalogue, pricing, academy information and enquiry form
- Supabase email-and-password registration and login
- Mandatory email verification before dashboard or course enrolment access
- Six-digit verification-code screen plus secure email-link callback
- Forgot-password and secure password-update flows
- Public self-registration is restricted to students; tutor and administration accounts are created privately by the Super Administrator
- Private student dashboards and student-owned Supabase profile records
- Row Level Security policies that restrict each profile to its authenticated owner
- Private-by-default Django REST permissions with explicit public content endpoints
- Browser security headers and private/no-store caching for authenticated routes
- Cloudflare D1 support for course progress and contact enquiries
- Branded student documents, letterhead and invoice previews
- Django CMS with a branded Jazzmin administration dashboard
- Admin-managed courses, modules, lessons, videos, resources, pages, pricing and enquiries

## Technology

- Next.js 16, React 19 and Vinext
- TypeScript and Tailwind CSS
- Supabase Auth and PostgreSQL
- Cloudflare Workers, D1 and Sites hosting
- Django 5.2, Django REST Framework, Jazzmin, Gunicorn with Uvicorn workers, Celery and Redis
- AWS-ready PostgreSQL, S3, NGINX and Docker services
- One Flower instance for Celery monitoring, plus Prometheus, Grafana and cAdvisor
- Six-hour encrypted PostgreSQL/media backups with weekly isolated restoration tests

## Environment

Copy `.env.example` to `.env.local` and set:

```env
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_your_key
SITE_URL=https://your-site.example.com
CMS_API_URL=https://your-cms.example.com/api/v1
```

Never commit a Supabase secret or service-role key. The website uses only a publishable key, with database access controlled by Row Level Security.

## Supabase setup

Apply the SQL files in `supabase/migrations/` in timestamp order. In Supabase Auth:

1. Enable email and password authentication.
2. Keep email confirmation required.
3. Add the production site URL and `/auth/confirm` callback to the redirect allow list.
4. Configure custom SMTP for delivery to external student email addresses.
5. Use `{{ .Token }}` in the confirmation email template when six-digit codes are required. The secure confirmation link is also supported.

## Development

```bash
npm ci
npm run build
```

The production bundle targets Cloudflare Workers. Hosted environment values are managed by the Sites platform and are not committed to Git.

## Error recovery

The public site includes branded recovery routes for HTTP 400, 403, 404, 429, 500, 502 and 503 responses, plus payment pending, payment cancelled, payment failed, expired sessions and lost connections. Automatic 404 and application-error boundaries use the same dependency-light design. Every recovery response carries an opaque `X-Correlation-ID` and displays a copyable support reference without exposing a stack trace or infrastructure detail.

Registration and enquiry drafts use short-lived `sessionStorage` entries in the current tab. Only explicitly allowed text and select fields are retained. Passwords, OTPs, tokens, consent controls, payment fields and uploads are excluded and successful submissions clear their drafts.

## Django administration

The AWS-ready administration service is in [`backend/`](backend/). Its setup and deployment instructions are in [`backend/README.md`](backend/README.md). The public website falls back to its bundled content until `CMS_API_URL` points to a deployed HTTPS Django service.

The backend disaster-recovery policy and operator runbook are in [`backend/docs/DISASTER_RECOVERY.md`](backend/docs/DISASTER_RECOVERY.md). Monitoring remains observational: Prometheus, Grafana, Flower, exporters or pgAdmin can fail without stopping the student platform.

## Load testing

The staging-only Locust suite covers public course discovery, account entry points, authenticated learning, progress, application checkout creation and payment-status polling. It includes normal, peak, sudden-spike, database-delay, Redis-loss, Celery-backlog and monitoring-outage scenarios with enforceable response-time and failure-rate limits. Direct PayFast traffic and the live Amaris hostname are blocked by default. See [`backend/load_tests/README.md`](backend/load_tests/README.md).

## Performance

Public page rendering no longer waits for authentication, global CMS content is fetched once per render, course lists use summary payloads, Django public reads use a failure-tolerant cache, and Celery's durable broker is isolated from the eviction-based response cache. Gunicorn, PostgreSQL, Redis, NGINX and container resource defaults are explicitly bounded and observable. Targets, sizing guidance and the measurement loop are in [`docs/PERFORMANCE.md`](docs/PERFORMANCE.md).

## Quality gates and releases

GitHub Actions now blocks releases on Python, Django, frontend, accessibility, Lighthouse, dependency, secret, Docker and container-security checks. Successful `main` builds promote an immutable backend image to staging; production requires a manual run, a protected GitHub environment approval, a pre-migration backup for high-risk changes and a successful post-deployment readiness check. See [`docs/CI_CD.md`](docs/CI_CD.md) for repository settings, protected secrets and webhook contracts.

Amaris remains **pre-production** until every professional acceptance criterion has approved evidence. The production workflow enforces the 20-item gate covering performance, WCAG 2.2 AA, mobile and no-JavaScript journeys, learning continuity, payments, permissions, caching, restoration, load capacity, email authentication, monitoring and cross-device quality. See [`docs/ACCEPTANCE_CRITERIA.md`](docs/ACCEPTANCE_CRITERIA.md).
