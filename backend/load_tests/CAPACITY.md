# Capacity verification

Capacity verification is deliberately separate from normal pull-request CI. The only trigger for `.github/workflows/capacity.yml` is `workflow_dispatch`.

## Progressive stages

A run may target one of these maximum levels:

`100 → 500 → 1,000 → 2,500 → 5,000 → 10,000 → 25,000 → 50,000`

The workflow always executes the lower levels first and stops at the first failed or unverifiable stage. The maximum verified capacity is therefore the highest **contiguous passing** level. Results are never extrapolated from a lower stage.

The 50,000-user statement is locked to this rule:

```text
MAXIMUM VERIFIED CONCURRENT USERS: <highest passing stage>
50,000 CONCURRENT USERS VERIFIED: YES / NO
```

`YES` is only produced when the 50,000-user stage itself runs, actually reaches at least 50,000 observed concurrent Locust users, and passes the request and infrastructure gates.

## Request evidence

Each stage records:

- actual maximum concurrent users observed
- requests per second (RPS)
- p50, p90, p95 and p99 response times
- overall failure percentage
- HTTP 5xx percentage
- request count and failure count
- Locust CSV and HTML evidence

Default capacity gates are intentionally stricter than merely “did not crash”:

- failure percentage ≤ 1.0%
- 5xx percentage ≤ 0.5%
- p95 ≤ 2,000 ms
- p99 ≤ 4,000 ms

Changing these values requires an explicit workflow/code change or environment override and must not be used to relabel a previously failing run as passing.

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

The default infrastructure resource gate is 90% of the measured CPU/RAM capacity. Redis rejected connections and PostgreSQL deadlocks must remain at zero during the measured window.

## Safety

Use a dedicated production-like capacity environment with synthetic data. Configure the protected GitHub `capacity` environment with:

- `CAPACITY_TARGET_URL`
- `CAPACITY_ALLOWED_HOSTS`
- `CAPACITY_PROMETHEUS_URL`
- representative endpoint paths, including `CAPACITY_LESSON_PATH` and `CAPACITY_PAYMENT_STATUS_PATH`
- a dedicated synthetic authentication credential in capacity-only secrets
- an optional Prometheus bearer token in `CAPACITY_PROMETHEUS_BEARER`

The workflow never enables direct PayFast load testing. It performs read-safe representative browsing/authenticated learning traffic and payment-status polling; it does not follow traffic into PayFast or generate a real charge.

Production targeting is blocked by default. The manual `allow_production` input must be explicitly enabled in addition to the target host being allow-listed. Prefer a production-like capacity environment rather than the live service.

## Load generator limits

Locust can use multiple local worker processes through the `locust_processes` workflow input. A GitHub-hosted runner may become the bottleneck at high concurrency. A stage is not considered verified merely because it was requested: the Locust evidence must show the requested concurrency was actually reached. For very large tests, run the same workload from appropriately sized/dedicated load-generator infrastructure before accepting the result.
