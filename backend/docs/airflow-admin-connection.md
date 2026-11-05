# Connect Airflow to the production Django Admin branch

## Verified baseline on 5 November 2026

The production backend uses `production-release-20260923` at
`ff4383ba8c4f2bf56174b88274ffd534ebfc80ed`, not GitHub `main`. That source has
private Grafana/Prometheus/Flower monitoring but no Airflow route or API client.
The Airflow Docker implementation merged to `main` in PR #229; the full-UI
launch change in PR #355 remains separate. This patch ports only the admin
integration onto the actual release baseline and preserves the existing proxy,
Grafana query authorization and monitoring status checks.

Render workspace `tea-csppi8l6l47c73dk9c90` currently reports both Django
backends suspended for billing and using native Python, with no separate
Airflow service. The shared Docker runtime is therefore not active on those
services. Source code or a visible admin link does not prove live Airflow
execution. No hosting plans, services, metadata roles or production data were
changed by this patch. No additional paid Airflow service is authorized.

## Admin integration

An active Django superuser gets **Monitoring → Airflow** in the sidebar,
**Open Airflow workflow monitor** on the admin home/monitoring pages and:

- `/admin/airflow/`: explicit unconfigured/unavailable states, required
  component health and the latest allowlisted DAG runs.
- `/admin/airflow/<dag_id>/`: the latest run and up to 100 task states.
  Dotted DAG IDs are supported. Unknown DAGs are rejected before API access.
- An optional **Open full Airflow UI** link with separate Airflow login.
  The URL must be reachable by the administrator's browser, protected by its
  own authentication and HTTPS. A private Render-only hostname will usually
  not work as a browser destination. No iframe, cookie or API-token forwarding.

Anonymous users are redirected to Django login; staff/student/tutor users
without superuser permission cannot use the Airflow monitor. API requests
are GET-only, bounded in time and size, certificate/hostname verified, and
never follow credential-bearing redirects. Configuration failures and upstream
exceptions are sanitized. Existing monitoring endpoints retain their controls.

## Runtime configuration and acceptance

Restore staging and use the existing Docker hosting strategy without adding
paid resources. Review the already merged
[shared-container runbook](https://github.com/BETHUELTHIPE/Amaris-Mathematics-Academy/blob/main/backend/ops/shared_airflow/README.md).
Runtime conversion, private metadata schema/role, certificates and resources
must be accepted in staging before production activation. This admin-only patch
does not copy that runtime into the release branch or convert a Render service.

Configure these settings through managed secrets/environment variables on the
Django service. Do not put token values in source, browser URLs or PR comments:

| Setting | Required value |
| --- | --- |
| `AIRFLOW_API_BASE_URL` | Private HTTPS origin, without `/api/v2`, credentials, query or fragment |
| `AIRFLOW_API_TOKEN` | Scoped read-only Viewer token; establish rotation/expiry handling |
| `AIRFLOW_API_CA_CERT_FILE` | Mounted trusted private CA file, if a private CA is used |
| `AIRFLOW_MONITORED_DAGS` | Comma-separated approved DAG IDs, default `amaris_service_health` |
| `AIRFLOW_UI_URL` | Optional authenticated HTTPS browser UI URL |
| `AIRFLOW_MONITORING_ENABLED` | Defaults to `false`; enable only following runtime acceptance |

From a trusted shell with the Django service's private network and managed
credentials, temporarily enable the read-only probe:

```bash
AIRFLOW_MONITORING_ENABLED=true python manage.py check_airflow \
  --dag-id amaris_service_health --max-run-age-minutes 30
```

Exit code 0 requires the authenticated, verified-TLS API to report healthy
metadata database, scheduler and DAG processor, an explicitly unpaused approved
health DAG, and a latest **scheduled** successful run with a timezone-aware
completion in the configured freshness interval. A reachable HTTP 200, manual
success, failed/paused/never-run DAG, stale completion, missing component,
expired token or bad certificate cannot establish readiness. The command
only reads; it never triggers, unpauses, retries, migrates or provisions anything.

After this passes, enable monitoring on staging and verify the actual admin
pages, optional UI login and Viewer write denial. Confirm scheduling continues,
token renewal, log retention, metadata backup/restore and shared-container
resource limits before promoting the exact tested revision. The health endpoint
reports scheduler health according to Airflow's heartbeat threshold; monitor
the scheduler independently as well.

Deployment still needs clean release gates and an application rollback path.
This patch contains no model/schema migration. Roll back application code and
disable the feature without changing Airflow metadata. Do not merge an unrelated
`main` release or overwrite the newer production monitoring gateway.

## Test boundary

CI runs formatting, lint, schema/migration checks, backend types and the Django
test suite against disposable PostgreSQL/Redis. Airflow HTTP responses in the
admin/readiness tests are isolated fixtures. Passing these tests verifies code
contracts; it does not establish a live Airflow runtime or successful production
DAG execution.

API reference:
[Airflow health checks](https://airflow.apache.org/docs/apache-airflow/3.3.2/administration-and-deployment/logging-monitoring/check-health.html).
