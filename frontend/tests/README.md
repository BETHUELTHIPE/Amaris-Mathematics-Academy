# Frontend test architecture

This directory defines the frontend production-readiness test taxonomy without moving stable existing tests unnecessarily.

- `unit/` — components, hooks, helpers and validation
- `integration/` — frontend/API boundaries and composed flows
- `e2e/` — browser journeys and role-sensitive flows

Existing root `tests/` files remain in place until individual tests are safely migrated.