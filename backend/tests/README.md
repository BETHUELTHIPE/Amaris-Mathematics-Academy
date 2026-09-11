# Backend test architecture

This directory provides the production-readiness test taxonomy without moving working application tests prematurely.

Existing Django tests remain in their current app locations (for example `content/tests.py`) until a specific test is migrated safely. New tests should be added under the most appropriate category below.

- `unit/` — isolated model/service/serializer/utility tests
- `integration/` — PostgreSQL/Redis/Celery/service integration tests
- `api/` — DRF endpoint behaviour and schema tests
- `authentication/` — registration, verification, login, reset, logout
- `authorization/` — role and object-level access/IDOR tests
- `payments/` — checkout, callbacks, idempotency, reconciliation
- `database/` — migrations, constraints, transactions, rollback
- `celery/` — queues, retries, idempotency, scheduled jobs
- `security/` — OWASP-aligned security regression tests

This structure is intentionally additive. Do not duplicate or move stable tests merely to satisfy folder layout.