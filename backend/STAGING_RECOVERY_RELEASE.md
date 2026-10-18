# Staging recovery release evidence

- Staging Render service: `srv-dam2iivcgkoc7383tq50`.
- Recovered base version: `af8709ce7549bff6760512aaa24bdbb718d17e34`.
- This branch retains Django `content.0014_announcement_media` migration graph already applied to the new staging Supabase project.
- Its release gate runs migration and booking tests against an isolated CI PostgreSQL database, and public-only live smoke checks.
- Production services and the original `staging` branch remain unchanged.
- This documentation-only commit exercises Render staging GitHub webhook and CI-gated auto-deploy. It introduces no application runtime changes.
- Genuine Supabase authenticated booking, PayFast sandbox notification, and transactional email inbox acceptance still require dedicated staging fixtures and notification-worker readiness.
