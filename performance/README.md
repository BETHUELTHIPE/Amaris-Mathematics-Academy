# Performance test architecture

The existing load tests under `backend/load_tests/` remain the current working Locust suite and are not moved unnecessarily.

This directory defines the target production-readiness structure:

- `locust/` — future distributed/capacity Locust scenarios and wrappers
- `k6/` — future k6 capacity, stress, spike and soak scenarios
- `reports/` — generated performance evidence (kept out of source control except documentation/placeholders)

Keep fast CI release gates separate from large capacity/stress testing.