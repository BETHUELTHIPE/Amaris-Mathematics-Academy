# Amaris Mathematics Academy

Online mathematics course platform for South African school, TVET, college and university students.

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

## Technology

- Next.js 16, React 19 and Vinext
- TypeScript and Tailwind CSS
- Supabase Auth and PostgreSQL
- Cloudflare Workers, D1 and Sites hosting

## Environment

Copy `.env.example` to `.env.local` and set:

```env
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_your_key
SITE_URL=https://your-site.example.com
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
