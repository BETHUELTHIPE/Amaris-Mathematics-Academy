# Production Kubernetes deployment contract

This directory is the production reference deployment for the Django/Celery data plane. The local `backend/docker-compose.yml` remains a development and single-host operations stack and is **not** the production secret-distribution mechanism.

## Required invariants

- Replace `REPLACE_WITH_FULL_GIT_SHA` with the exact immutable image created by the release workflow. Never deploy `:latest`.
- Create `amaris-secrets` from the production secret manager at deploy time. Do not commit a Secret manifest or plaintext values.
- `DATABASE_URL_DIRECT` points to the managed PostgreSQL primary and is available only to PgBouncer/recovery jobs.
- `DATABASE_URL_POOLED` points to the `pgbouncer` service and is used by Django and Celery.
- `DJANGO_SECRET_KEY`, Redis URLs, storage credentials, payment credentials and provider API credentials must come from the secret manager.
- The web deployment starts at three replicas and may scale to 24 replicas (8x headroom) at 70% CPU. Readiness gates PostgreSQL before traffic is sent to a pod.
- PgBouncer uses transaction pooling. Connection limits must be validated against the managed database before each material scale change.
- Critical/default Celery work is isolated from notification work so email or other low-priority I/O cannot starve payment reconciliation or learning operations.
- Run the `amaris-cache-warm` job before scheduled enrolment, examination or result-publication peaks.
- TLS allows only TLS 1.2/1.3. cert-manager starts renewal 14 days before expiry and Prometheus independently alerts when a probed certificate has less than 14 days remaining.

## Deployment sequence

1. Build and scan the exact Git SHA in CI.
2. Create/update the production secret object from the external secret manager.
3. Replace the immutable image placeholder in `production.yaml`.
4. Apply PgBouncer and worker resources, then the web deployment/HPA/PDB.
5. Wait for all readiness probes to pass.
6. Run the cache-warm job for scheduled peaks.
7. Apply `tls.yaml` only when this cluster owns the public hostname and the `letsencrypt-production` ClusterIssuer is already configured.
8. Run the safe post-deployment smoke/student journey and monitor the release. Failed health or journey checks must trigger rollback to the previously healthy immutable image.

The hosting platform may implement an equivalent managed service instead of Kubernetes, but it must preserve these same invariants: minimum three healthy web instances, 8x burst headroom, 70% CPU scale trigger, transaction connection pooling, separate critical/notification workers, managed secrets, readiness-before-traffic, and immutable rollback identity.
