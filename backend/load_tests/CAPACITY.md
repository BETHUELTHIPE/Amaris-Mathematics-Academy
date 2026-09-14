# Capacity verification

Capacity verification is deliberately separate from normal pull-request CI. The only trigger for `.github/workflows/capacity.yml` is `workflow_dispatch`.

## Progressive stages

A run may target one of these maximum levels:

`100 → 500 → 1,000 → 2,500 → 5,000 → 10,000 → 25,000 → 50,000`

The workflow always executes the lower levels first and stops at the first failed or unverifiable stage. The maximum verified capacity is therefore the highest **contiguous passing** level. Results are never extrapolated from a lower stage.

Capacity reporting remains separate from production readiness:

```text
PRODUCTION READINESS:
NOT EVALUATED BY CAPACITY TESTING

MAXIMUM VERIFIED CONCURRENT USERS:
<highest contiguous passing stage, or 0 when no capacity stage has passed>

50,000 CONCURRENT USERS VERIFIED:
YES / NO
```

`YES` is only produced when the 50,000-user stage itself runs, reaches at least 50,000 observed concurrent Locust users, sustains that target for essentially the configured hold period, and passes the request and infrastructure gates.

## Request evidence

Each stage records:

- actual maximum concurrent users observed
- target hold seconds required and actually sustained
- requests per second (RPS)
- p50, p90, p95 and p99 response times
- overall failure percentage
- HTTP 5xx percentage
- request count and failure count
- Locust CSV and HTML evidence

Capacity request gates are not allowed to be weaker than the normal release gate:

- failure percentage ≤ 1.0%
- 5xx percentage ≤ 0.1%
- p95 ≤ 1,000 ms
- p99 ≤ 2,000 ms

Environment values may make these limits stricter, but `CapacityThresholds` rejects any override that would weaken them. A passing result therefore cannot be manufactured by relaxing thresholds after a poor run.

The requested concurrency must be held for at least the configured hold period minus a 15-second sampling grace. Merely touching the target user count briefly does not establish capacity.

## Infrastructure evidence

The capacity report queries the existing Prometheus stack. Required measurements include:

- host CPU and RAM
- PostgreSQL exporter availability, active connections, deadlocks, PostgreSQL container CPU and RAM
- Redis broker availability, memory use, connected clients, rejected connections, CPU and RAM
- Redis cache availability and memory use
- Gunicorn/Django scrape availability plus web-container CPU and RAM
- Celery/Flower scrape availability, worker-online state, worker CPU and RAM
- Celery executing/prefetched task metrics when Flower exposes samples during the window

A required Prometheus metric that cannot be measured makes the capacity stage **NOT VERIFIED**. Missing telemetry is never treated as zero.

The infrastructure resource gate is capped at 90% CPU/RAM utilisation. Environment values may make that gate stricter but cannot raise it above 90%. Redis rejected connections and PostgreSQL deadlocks must remain at zero during the measured window.

## Safety

Use a dedicated production-like capacity environment with synthetic data. Configure the protected GitHub `capacity` environment with:

- `CAPACITY_TARGET_URL`
- `CAPACITY_ALLOWED_HOSTS`
- `CAPACITY_PROMETHEUS_URL`
- representative endpoint paths, including `CAPACITY_LESSON_PATH` and `CAPACITY_PAYMENT_STATUS_PATH`
- a dedicated synthetic authentication credential in capacity-only secrets
- an optional Prometheus bearer token in `CAPACITY_PROMETHEUS_BEARER`

The workflow never enables direct PayFast load testing. It performs read-safe representative browsing/authenticated learning traffic and payment-status polling; it does not follow traffic into PayFast or generate a real charge.

Production targeting is disabled in the workflow. Capacity verification must use a dedicated capacity/staging target that is explicitly allow-listed through `CAPACITY_ALLOWED_HOSTS`.

## Load generator limits

Capacity runs up to 1,000 users may use the GitHub-hosted generator for exploratory/low-stage verification. Any requested maximum above 1,000 users requires the `self-hosted` load-generator option and therefore a dedicated runner with sufficient CPU, RAM, file descriptors and network capacity.

The workflow records the selected runner, CPU count, total memory, open-file limit and Locust worker-process count as evidence. Locust uses `FastHttpUser` for the capacity workload and can use multiple local worker processes through the `locust_processes` input.

A high stage is still **not** considered verified merely because a self-hosted runner was selected. The test must actually reach and sustain the requested concurrency, pass the HTTP/error gates, and retain complete PostgreSQL, Redis, Gunicorn/Django, Celery and system telemetry.
