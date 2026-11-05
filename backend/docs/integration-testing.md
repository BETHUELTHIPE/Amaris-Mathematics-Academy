# Integration testing policy

The integration suite deliberately separates real infrastructure boundaries from paid or remote third-party services.

## Real integration boundaries

The suite must exercise these with real test infrastructure:

- Django ↔ PostgreSQL
- Django ↔ Redis through the Django cache backend
- Django ↔ Celery through a real Redis broker/result backend and an in-process Celery worker
- Django ↔ frontend CMS API contract (`frontend/lib/cms.ts` ↔ Django `/bootstrap/` and `/courses/` payloads)
- Django ↔ storage abstraction using an isolated local filesystem adapter in CI

GitHub Actions already provides PostgreSQL and Redis service containers for the backend quality job. When those services are expected in CI, an unavailable dependency is a failure, not a skipped pass. Local runs without the optional infrastructure may skip the relevant real-infrastructure checks.

## External providers

Do not make live calls from integration tests to:

- PayFast
- email delivery providers
- WhatsApp
- SMS providers
- Zoom
- OpenAI
- Gemini
- YouTube or other external video services

Use sandbox or mock adapters instead. Email tests use Django's in-memory backend. PayFast tests must use verified synthetic payment records or a sandbox adapter and must never create a real charge. AI/video/communications tests must use deterministic mocks and must not require paid API credentials.

The integration suite rejects known live/paid provider credentials when they are injected into this test boundary.

## Data safety

Use only deterministic or synthetic fixtures. Never use real student personal information, real payment details, or production credentials.

## Reporting

A passing integration suite proves only the integrations exercised by the suite. It does not prove production readiness by itself and it does not verify any concurrent-user capacity claim.
