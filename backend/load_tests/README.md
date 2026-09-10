# Amaris load testing

The Locust suite measures public browsing, account entry points, authenticated learning and the application-owned checkout workflow. It is designed for an isolated local or staging environment containing disposable students, courses, lessons and orders.

It never sends payment traffic to PayFast. Checkout requests target only the Amaris order-creation path and disable redirect following. Absolute endpoint URLs are rejected, known PayFast hosts are blocked, and the live Amaris hostname is blocked unless production testing has separately received explicit written authorisation.

## Pre-production acceptance criteria

These limits are release requirements, not targets to relax after a poor result.

| Traffic profile | Users and duration | Maximum failure rate | Overall p95 | Overall p99 |
|---|---:|---:|---:|---:|
| Smoke | 5 users, 35 seconds | 1% | 1,000 ms | 2,000 ms |
| Normal | 20 users, 12 minutes | 1% | 1,000 ms | 2,000 ms |
| Peak | 100 users, 20 minutes | 2% | 1,500 ms | 3,000 ms |
| Sudden spike | 20 → 200 users, 5 minutes | 3% | 2,000 ms | 4,000 ms |
| Degraded dependency | 10 users, 105 seconds | 5% | 3,000 ms | 6,000 ms |

Endpoint p95 limits are stricter where students wait interactively:

| Request group | Normal | Peak | Spike | Degraded |
|---|---:|---:|---:|---:|
| Homepage, catalogue, search, course details, registration/login pages | 750 ms | 1,000 ms | 1,500 ms | 2,500 ms |
| Dashboard, protected lesson, payment-status polling | 1,000 ms | 1,500 ms | 2,000 ms | 3,000 ms |
| Registration/login submission, progress and checkout creation | 1,500 ms | 2,000 ms | 2,500 ms | 4,000 ms |

The suite exits non-zero when a configured limit is breached. A production launch also requires every full-journey endpoint to produce samples, recovery to a healthy readiness response within two minutes after a fault is removed, and no lost verified payment or progress record during post-test reconciliation.

## Install and run

From `backend/`:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-load.txt
cp .env.example .env
docker compose up --build -d
LOADTEST_PROFILE=smoke LOADTEST_TARGET_URL=http://127.0.0.1:8080 load_tests/run.sh
```

Use `normal`, `peak`, `spike` or `degraded` for `LOADTEST_PROFILE`. CSV and HTML reports are written to `load_tests/results/` and are ignored by Git.

## Full authenticated journey

Create a dedicated verified staging student, a paid staging enrolment, one course and lesson, and one pending test order. Never use a real student's session or production payment reference. Then configure:

```env
LOADTEST_ENVIRONMENT=staging
LOADTEST_ALLOWED_HOSTS=staging.amaris.example
LOADTEST_TARGET_URL=https://staging.amaris.example
LOADTEST_REQUIRE_FULL_JOURNEY=true
LOADTEST_ALLOW_WRITES=true

LOADTEST_AUTH_BEARER=
LOADTEST_COOKIE_HEADER=
LOADTEST_SESSION_COOKIE_NAME=
LOADTEST_SESSION_COOKIE_VALUE=
LOADTEST_LOGIN_EMAIL=load-test-student@example.invalid
LOADTEST_LOGIN_PASSWORD=
LOADTEST_REGISTRATION_PASSWORD=
LOADTEST_REGISTRATION_EMAIL_DOMAIN=loadtest.staging.example

LOADTEST_REGISTRATION_SUBMIT_PATH=/api/test-support/registration/
LOADTEST_LOGIN_SUBMIT_PATH=/api/test-support/login/
LOADTEST_LESSON_PATH=/dashboard/courses/load-test-course/lessons/load-test-lesson/
LOADTEST_PROGRESS_PATH=/api/v1/progress/
LOADTEST_CHECKOUT_PATH=/checkout/course/load-test-course/create-order/
LOADTEST_PAYMENT_STATUS_PATH=/api/v1/orders/load-test-order/status/
LOADTEST_COURSE_ID=load-test-course
LOADTEST_LESSON_ID=load-test-lesson
```

Supply either a short-lived bearer token, the complete staging cookie header, or a single test-session cookie through the protected staging secret store. Login and registration credentials must also be staging-only secrets. `LOADTEST_REGISTRATION_EMAIL_DOMAIN` must route to a non-delivering staging email sink or approved catch-all account. The application team must map the example paths to the deployed API before enabling `LOADTEST_REQUIRE_FULL_JOURNEY`; the run intentionally fails when any protected/write path or credential is missing.

Do not put tokens, passwords, cookies or student details in shell history, workflow variables, committed files, test names, report filenames or Locust request names. Rotate the test session after each run and remove generated accounts/orders according to the staging retention policy.

## Controlled dependency-failure tests

The fault runner is intentionally restricted to a local Compose staging stack. It refuses remote targets and requires both safety controls:

```bash
export LOADTEST_ENVIRONMENT=staging
export LOADTEST_ALLOW_CHAOS=true
export LOADTEST_TARGET_URL=http://127.0.0.1:8080

load_tests/run-failure-scenario.sh slow-database
load_tests/run-failure-scenario.sh redis-interruption
load_tests/run-failure-scenario.sh celery-backlog
load_tests/run-failure-scenario.sh monitoring-failure
```

- **Slow database:** holds an exclusive course-table lock for 45 seconds while requests continue, then verifies recovery.
- **Redis interruption:** stops Redis during the degraded test, restarts it and confirms Django readiness remains healthy.
- **Celery backlog:** pauses the worker, queues 200 idempotent publishing tasks, resumes the worker and allows Flower/Prometheus to confirm the queue drains.
- **Monitoring failure:** stops Flower, Prometheus, Grafana, exporters and pgAdmin while student traffic continues, then restarts them.

The cleanup trap always requests restart of affected services. Before a test, take a staging backup, confirm no production network is connected, announce the maintenance window and have an operator watch database, queue and container metrics. Afterward, run payment reconciliation, verify enrolments/progress, confirm queue depth returns to normal and attach the HTML/CSV evidence to the release record.

## GitHub Actions

`Load Tests` is separate from pull-request CI because sustained traffic needs an isolated staging environment. Manual runs select normal, peak or spike traffic and may enable the protected full journey. A weekly scheduled run uses the smoke profile and safe public requests. Configure the `staging` environment values and secrets documented in the workflow; GitHub environment protection prevents credentials from being exposed to unapproved jobs.
