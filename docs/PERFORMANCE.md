# Performance architecture and operating budgets

This document defines the production performance baseline for Amaris Mathematics Academy. Values are release gates, not promises for an unmeasured environment. Confirm them in staging with production-sized data before launch.

## User-facing objectives

| Signal | Target |
|---|---:|
| Core Web Vitals | LCP <= 2.5 s, INP <= 200 ms, CLS <= 0.10 at p75 |
| Public API reads | p95 <= 500 ms, p99 <= 1 s |
| Authenticated Django reads | p95 <= 750 ms |
| Checkout creation | p95 <= 1 s, excluding PayFast |
| Error rate | < 1% normally, < 2% at agreed peak |
| Lighthouse performance | >= 85 on tested public pages |
| Largest browser JavaScript chunk | <= 250 KiB uncompressed |
| Largest stylesheet | <= 200 KiB uncompressed |
| Homepage hero | <= 200 KiB |

## Browser and Next.js

- Global CMS brand and navigation use one `/bootstrap/` request and React request memoisation.
- Authentication is a small client island. Public pages render immediately; the header checks `/api/auth-state` after paint instead of making every public page wait on Supabase.
- Supabase JWT claims are verified locally against cached signing keys with `getClaims()` on protected server routes.
- The Supabase proxy only runs on authentication, dashboard and protected API paths.
- The hero uses WebP, reserves its display dimensions and is preloaded only on the homepage.
- CMS fetches use a four-second upper bound and stale-safe bundled fallback content.
- CI enforces asset budgets and Lighthouse thresholds after every production build.

## Django queries and cache

- Catalogue list responses use a summary serializer and do not prefetch module and lesson trees. A course detail request prefetches that tree in bounded queries.
- Public read endpoints are cached for five minutes; the shell bootstrap is cached for one minute. Content saves and deletes invalidate the shared namespace.
- Redis cache failures degrade to database reads and never fail a public request.
- The cache has a dedicated `allkeys-lru` Redis service. The Celery broker is separate, persistent and uses `noeviction` so cache pressure cannot discard tasks.
- Composite and partial indexes cover published content ordering, student status/history and payment reconciliation.
- PostgreSQL enables `pg_stat_statements`, bounded statements, idle-transaction cleanup and memory settings appropriate to the default 1 GiB database container. Recalculate these values for the actual production host.
- Django keeps healthy database connections for ten minutes. If total web and Celery concurrency grows near `POSTGRES_MAX_CONNECTIONS`, deploy PgBouncer or the managed provider's transaction pool before increasing workers.

The init script enables `pg_stat_statements` for new volumes. For an existing volume, restart PostgreSQL with `shared_preload_libraries=pg_stat_statements`, then run the following once with the controlled migration role:

```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

Migration jobs explicitly disable the ordinary 30-second statement timeout; application requests retain it so unexpectedly expensive queries cannot occupy a worker indefinitely.

Review slow queries weekly in staging and production. Use normalised `pg_stat_statements` data; never export query text containing personal or payment information into shared dashboards.

## Gunicorn and Celery

- Gunicorn uses Uvicorn workers, configurable concurrency, 60-second request timeouts, 30-second graceful shutdown, keep-alive reuse and worker recycling with jitter.
- Start with three web workers. Scale from measured CPU saturation and latency, not the CPU-count formula alone. Keep at least 20% memory and database-connection headroom.
- Celery uses late acknowledgement, lost-worker rejection, prefetch of one, bounded publish retries, time limits and worker recycling by task count and memory.
- Increase Celery concurrency only after checking queue wait time, memory per task and database capacity. Split slow CPU tasks from email/I/O tasks into dedicated queues when their service levels diverge.
- Payment reconciliation streams candidates in chunks and locks rows with `skip_locked`, allowing safe concurrent runs without loading all identifiers into memory.

## Containers and NGINX

- Compose defines CPU and memory ceilings for PostgreSQL, both Redis roles, web, Celery, Beat and NGINX. Treat defaults as a starting point and tune from cAdvisor trends.
- NGINX reuses upstream connections, buffers ordinary responses, compresses text/JSON assets and serves fingerprinted static files with a one-year immutable cache policy.
- Prometheus, Grafana, Flower, exporters and pgAdmin remain observational services. They are not startup dependencies for web, registration, lessons, checkout or payment reconciliation.

## Measurement loop

1. Run the full CI build and performance-budget check.
2. Load production-sized anonymised data in staging.
3. Run the normal, peak and spike Locust profiles from a separate load generator.
4. Compare p50/p95/p99 latency, error rate, database CPU/locks, cache hit ratio, Redis memory, queue age and container throttling.
5. Change one capacity or query variable at a time, repeat the same profile and retain the report.
6. Block release when any acceptance threshold fails or when the result lacks a representative dataset.
