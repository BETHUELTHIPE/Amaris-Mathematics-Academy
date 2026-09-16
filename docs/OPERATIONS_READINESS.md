# Production operations readiness

This runbook implements the operating controls required by the production-performance architecture. It supplements `backend/docs/DISASTER_RECOVERY.md`, `docs/PERFORMANCE.md`, and `docs/CI_CD.md`.

## Ownership and service objectives

The **Primary On-Call Engineer** owns initial alert response and service restoration. The **Secondary On-Call Engineer** is the escalation point when the primary does not acknowledge a critical alert within 10 minutes or requests assistance. The **Incident Commander** coordinates Sev1/Sev2 communications and decisions. The **Release Owner** owns rollback decisions during deployment. The **Information Officer / privacy owner** approves retention exceptions and deletion requests.

The production objectives are release gates, not assumed capability: public/API p99 <= 1 second, public p95 <= 500 ms, authenticated reads p95 <= 750 ms, checkout/write p95 <= 1 second, normal error rate <1%, peak error rate <2%, and monthly public-read availability >=99.5%. Prometheus alerts enforce the latency/error operating budgets and Alertmanager routes them to the on-call receiver. PayFast webhook outcome and verification latency are measured independently from application latency.

## Severity model

| Severity | Definition | Initial response | Examples |
|---|---|---:|---|
| Sev1 | Widespread outage, payment/access integrity risk, confirmed data loss, or security incident affecting production | 5 minutes | public service unavailable; corrupted payment state; database unavailable with no healthy failover |
| Sev2 | Major degradation or partial outage with material student impact but safe data integrity | 15 minutes | sustained p99/error SLO breach; Celery critical queue backlog; Redis cache failure causing database pressure |
| Sev3 | Limited degradation, operational warning, or non-urgent defect with workaround | 4 business hours | restore-test stale; one monitoring component unavailable; approaching capacity threshold |

Sev1 and Sev2 incidents require a blameless post-incident review within five business days. The review must create tracked corrective actions and, where relevant, update alert thresholds, acceptance tests, capacity assumptions, runbooks, or release gates.

## Escalation path

1. Alertmanager notifies the Primary On-Call Engineer.
2. If a critical alert is not acknowledged within 10 minutes, escalate to Secondary On-Call.
3. Sev1 automatically requires an Incident Commander and Release Owner.
4. Payment, privacy, or security incidents also notify the relevant business/privacy/security owner.
5. If a provider dependency is involved, open a provider incident while continuing internal mitigation; do not wait for the provider before protecting student data or payment integrity.

The on-call receiver is supplied through the `ALERTMANAGER_WEBHOOK_URL` secret. A release cannot claim alerting is operational until a test alert has been delivered, acknowledged, and recorded in production-readiness evidence.

## PostgreSQL connection exhaustion

**Trigger:** `AmarisPostgresConnectionsHigh`, rising request latency, or connection errors.

1. Stop nonessential batch work and avoid increasing web/Celery concurrency.
2. Confirm application traffic is using `DATABASE_URL_POOLED` through PgBouncer.
3. Inspect `pg_stat_activity`, longest transactions, blocked sessions, and `pg_stat_statements` without exporting personal/payment values.
4. Terminate only clearly abandoned sessions according to the database operating policy; do not kill active payment transactions blindly.
5. If pool saturation is caused by traffic, scale application replicas only within the connection budget or raise PgBouncer client capacity without exceeding server-connection limits.
6. If saturation is caused by a slow query, disable the affected risky feature with `AMARIS_FEATURE_FLAGS` or roll back the release.
7. Record peak connections, pool utilisation, lock waits and corrective action.

A read replica is **deferred by design** until measurements show sustained read pressure that cannot be resolved with indexes, cache, pooling, or vertical database capacity. Reporting/analytics must not be moved to a replica until lag tolerance and payment consistency requirements are documented and tested.

## Celery queue backlog

**Trigger:** `AmarisCeleryQueueAgeHigh` or visible critical queue growth.

1. Check Redis health and Flower metrics.
2. Protect the `critical` queue first. Notification work remains isolated on the `notifications` worker.
3. Increase critical-worker replicas/concurrency only after checking memory per task and PostgreSQL connection headroom.
4. Do not redirect critical jobs to notification workers during an incident.
5. Terminal task failures are parked as sanitized metadata in `amaris:celery:dead-letter`; review task name, error class and task ID without storing task arguments.
6. Retry only after the root cause is understood; important tasks must remain idempotent.

## Redis/cache incident

Use the detailed Redis/Celery recovery procedure in `backend/docs/DISASTER_RECOVERY.md`. Public requests must degrade to uncached database reads. If cache loss causes database pressure, temporarily reduce nonessential traffic/work and restore cache before raising database connection limits.

## PayFast timeout or webhook failure spike

**Trigger:** `AmarisPaymentWebhookFailureRateHigh`, `AmarisPaymentWebhookP95LatencyHigh`, or provider incident.

1. Keep browser redirects non-authoritative. Only verified server callbacks may grant paid access.
2. Do not disable signature/source/server verification to restore throughput.
3. Preserve retryable webhook events and allow bounded retries/reconciliation.
4. Check provider status and network reachability; separate provider latency from internal application latency in the incident record.
5. Run reconciliation only against payments already carrying gateway verification evidence. Never mark a payment paid manually from a screenshot or client state.
6. Escalate unresolved paid-access mismatches for authorised review.

## TLS/certificate expiry

**Trigger:** `AmarisTLSCertificateExpiring` (<14 days).

1. Confirm whether the public edge is provider-managed or cert-manager-managed.
2. For cert-manager, inspect Certificate/CertificateRequest/ACME challenge state and DNS/HTTP validation.
3. For a managed edge, open a provider incident immediately if automatic renewal has not occurred.
4. Do not bypass TLS or serve HTTP as a workaround. Maintain TLS 1.2/1.3 only.
5. After renewal, verify the new expiry with Blackbox Exporter and an external TLS check.

## Rollback and release target

Rollback is the preferred response to a newly introduced application regression when the database schema remains backward-compatible. The operational target is to restore the previous known-good immutable image and healthy critical student journey within **10 minutes** of the rollback decision.

Every production release must retain the previous two known-good immutable image references. Health failure after a deployment invokes rollback. High-risk or destructive migration changes require separate review; use expand/migrate/contract and a verified pre-migration recovery point. Never improvise destructive SQL during rollback.

A quarterly rollback exercise must record detection time, rollback decision time, restored Git SHA/image, health result, student-journey result and achieved recovery time.

## Feature flags and peak-event change freeze

High-risk features must be disabled by default and exposed through `AMARIS_FEATURE_FLAGS`. A flag is enabled only after staging acceptance and must have an owner, rollback condition and removal date.

For scheduled enrolment, examination, results or other high-traffic events, establish a change freeze beginning at least **24 hours before** the expected peak and ending after traffic has returned to normal and the release owner approves reopening changes. During the freeze, only Sev1/Sev2 fixes may deploy, using the normal protected release and rollback process. Pre-warm the public cache immediately before the peak and verify minimum replicas/capacity headroom.

## Signing-key and credential rotation

Authentication/provider signing keys and production credentials must be stored in the platform secret manager, not source control or ordinary production `.env` files. Rotate credentials after suspected exposure and on the organisation's scheduled rotation cadence. When a provider supports overlapping keys, deploy the new key, verify both old/new validation during the overlap, then revoke the old key. Stale signing-key failures are treated as an authentication incident and must not be bypassed by accepting unverified identity tokens.

## Data retention and deletion policy

This is an internal operating policy and does not replace legal advice or statutory retention requirements.

- Synthetic load/E2E identities and generated test data: delete within 30 days unless attached to an active incident/evidence record.
- Detailed application/edge logs: retain 90 days by default; avoid logging secrets, full payment payloads, authentication tokens, or unnecessary personal data.
- Security, release, backup/restore and production-acceptance evidence: retain according to the audit/recovery policy, with a minimum sufficient to prove the current release and recent recovery exercises.
- Student/account/payment records: retain only for the active service purpose plus applicable legal/accounting requirements; deletion requests are reviewed by the privacy owner so records under legal/financial hold are not destroyed incorrectly.
- Approved deletions must propagate to primary application records, derived profiles and eligible backups according to the backup retention cycle. Record the request ID, approval, systems affected and completion date without copying the deleted personal data into the audit log.

Retention exceptions require the Information Officer/privacy owner and a documented reason/end date.

## Performance review cadence

- Weekly: inspect normalized `pg_stat_statements`, cache hit ratio, Redis memory, Celery queue age, p50/p95/p99 latency and error rates.
- Before a material release or traffic event: load production-sized anonymised data in staging, warm cache, run the representative normal/elevated/peak or spike profile from the dedicated generator, and retain results.
- First two weeks after a major launch/capacity change: review telemetry daily and tune warning thresholds only from observed data. Do not weaken release acceptance limits simply to make a failing test pass.
- Quarterly: disaster-recovery and rollback exercise.

## Post-incident review template

**Incident:**
**Severity:**
**Start / detection / mitigation / recovery times:**
**Customer/student impact:**
**Data/payment integrity impact:**
**Detection source:**
**Timeline:**
**Contributing technical/operational conditions:**
**What worked:**
**What did not work:**
**Corrective actions (owner + due date):**
**Tests/alerts/runbooks/acceptance thresholds updated:**
**Follow-up verification evidence:**

Focus on systems, assumptions, controls and decision context rather than individual blame.
