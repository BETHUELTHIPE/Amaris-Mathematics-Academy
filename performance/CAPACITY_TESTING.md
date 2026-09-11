# Amaris Capacity Testing

Capacity testing is intentionally separate from normal pull-request CI. PR CI may validate load-test code and safety contracts, but it must not run large-scale capacity tests.

## Approved progression

Execute stages in this order and stop at the first failed stage:

1. 100 concurrent users
2. 500 concurrent users
3. 1,000 concurrent users
4. 2,500 concurrent users
5. 5,000 concurrent users
6. 10,000 concurrent users
7. 25,000 concurrent users
8. 50,000 concurrent users

A higher level is not verified merely because the harness supports it. Only an actually executed test with recorded evidence may be reported as verified capacity.

## Required measurements per stage

Application traffic:
- requests per second (RPS)
- p50 response time
- p90 response time
- p95 response time
- p99 response time
- total failure percentage
- HTTP 5xx percentage

Infrastructure for the exact same test window:
- application CPU and RAM
- PostgreSQL CPU/connections/IO/latency/locks where available
- Redis CPU/memory/clients/latency/evictions where available
- Gunicorn worker utilisation, restarts, timeouts and saturation indicators
- Celery active/reserved/retried/failed tasks, queue depth and worker CPU/RAM

Store the application result and monitoring export together under `performance/reports/` with the tested commit SHA, target environment, start/end UTC timestamps, requested concurrency and generator topology.

## Safety rules

Use staging or another explicitly authorised capacity environment by default. The live Amaris production hostname is blocked by the existing Locust configuration and the k6 harness unless an explicit production override is supplied. Never point capacity tests directly at PayFast or another live payment endpoint. Do not put credentials in target URLs or committed files.

For authenticated/full-journey Locust runs, use dedicated staging credentials or session material supplied through secret environment variables. Write operations must remain disabled unless the test environment and data-cleanup plan explicitly permit them.

## Locust

The existing `backend/load_tests/locustfile.py` remains the full application-journey harness. It validates allowed hosts, blocks production by default, can require the complete authenticated journey, and enforces response-time/failure SLOs.

For a fixed capacity stage, run Locust headlessly with distributed workers when the generator host cannot sustain the requested concurrency. Example shape:

```bash
LOADTEST_ENVIRONMENT=staging \
LOADTEST_ALLOWED_HOSTS=staging.example.internal \
locust -f backend/load_tests/locustfile.py \
  --host https://staging.example.internal \
  --headless -u 100 -r 20 -t 10m \
  --csv performance/reports/locust-100
```

At large stages, use Locust master/workers or multiple generators and record generator CPU/RAM so generator saturation is not mistaken for application saturation.

## k6

`performance/k6/capacity.js` provides a fixed-concurrency staged harness for the public read journey. It only accepts the approved concurrency values.

Example:

```bash
CAPACITY_TARGET_URL=https://staging.example.internal \
CAPACITY_ALLOWED_HOSTS=staging.example.internal \
CAPACITY_ENVIRONMENT=staging \
CAPACITY_USERS=100 \
CAPACITY_DURATION=10m \
CAPACITY_RAMP=2m \
k6 run performance/k6/capacity.js
```

The k6 result records RPS, p50, p90, p95, p99, failures and 5xx rate. Infrastructure metrics still have to be captured from Prometheus/Grafana/CloudWatch or the deployment platform for the same window.

## Pass/fail policy

Do not weaken thresholds just to obtain a green result. If a stage breaches latency, failure, 5xx or infrastructure safety limits, mark that stage failed, investigate the bottleneck, change the application/infrastructure, then repeat that same stage before moving higher.

The verified maximum capacity is the highest consecutive stage that actually passed with both application and infrastructure evidence. If 25,000 passes and 50,000 fails, the verified maximum is 25,000, not 50,000.

Never state that Amaris supports 50,000 concurrent users unless a real 50,000-user test has completed successfully with acceptable application and infrastructure metrics.
