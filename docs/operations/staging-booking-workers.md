# Staging booking workers: prepared deployment plan

Status: PREPARED ONLY. No resources have been purchased or provisioned.

Three always-on processes are required: a critical/default queue worker, a notifications queue worker and exactly one Celery Beat scheduler. Reuse the existing staging broker (red-dam2golbedkc73ae6ph0, noeviction), staging Supabase project atyhhjwwxgzeurnwayay and the existing staging backend source. Do not consume production queues or use the monitoring-only worker.

## Concrete resources

| Service | Source branch | Command after cd backend | Compute |
| --- | --- | --- | --- |
| amaris-staging-critical-worker | ops/staging-known-good-af8709c-20261019 | celery -A amaris_cms worker --loglevel=INFO --queues=critical,default --concurrency=1 --events --hostname=staging-critical@%h | 0.5c-512mb |
| amaris-staging-notification-worker | ops/staging-known-good-af8709c-20261019 | celery -A amaris_cms worker --loglevel=INFO --queues=notifications --concurrency=1 --events --hostname=staging-notifications@%h | 0.5c-512mb |
| amaris-staging-beat | ops/staging-known-good-af8709c-20261019 | celery -A amaris_cms beat --loglevel=INFO --pidfile=/tmp/celerybeat.pid --schedule=/tmp/celerybeat-schedule | 0.5c-512mb |

Common settings: type background_worker, native Python runtime, Frankfurt region, one instance, manual deployment, repository BETHUELTHIPE/Amaris-Mathematics-Academy, build command cd backend && pip install -r requirements.txt. Start from the exact reviewed staging commit; do not switch the staging web or frontend branch. No database migration or new datastore is part of this plan.

Render's current smallest worker compute is listed at US$7/month. Three workers therefore add an estimated US$21/month excluding tax and usage. This is separate from the previously approved monitoring budget. Provision only after that additional recurring cost is explicitly approved. Pricing: https://render.com/pricing ; compute IDs: https://render.com/docs/compute-plans .

## Protected configuration

Copy the existing staging web service's relevant runtime values directly inside a protected operation; never paste or commit their values:
- Django secret, DATABASE_URL and its SSL/database safeguards.
- CELERY_BROKER_URL and CELERY_RESULT_BACKEND from the staging broker, with exact staging/production broker identity comparison.
- Supabase URL, private storage endpoint, bucket bindings and S3 access credentials.
- SMTP host, port, TLS/SSL settings, host user, app password and default sender for the notifications worker.
- Existing finance encryption key if encrypted tutor account data is used.

Fail closed unless the source is srv-dam2iivcgkoc7383tq50 in workspace tea-csppi8l6l47c73dk9c90, database/Auth/storage bind to the staging project, PayFast is sandbox, and the staging broker differs from the production broker. No live PayFast credentials are required for the scheduler or delivery workers. Never copy the Render API key into a worker.

## Apply and acceptance

The Render connector supports inspection and logs but currently does not expose background-worker creation. After cost approval, use a protected, reviewed GitHub operation for those creation calls, then use the Render connector to monitor the resulting deployments. Check for existing service names before any create request; adopt matching resources on retry instead of creating duplicates.

Verify:
1. All three exact-source deployments are live and have no startup errors.
2. Celery inspect ping and active_queues show the named staging workers consuming only their intended staging queues.
3. Beat emits a scheduled task that the notifications worker completes autonomously.
4. A genuine sandbox callback settles the approved staging student's booking.
5. The worker sends the matching PDF receipt, stores its private archive, and the approved Gmail inbox contains the correct attachment.
6. A due reminder is delivered once; retry/duplicate ITNs do not duplicate fulfillment or receipts.

Configuration or a live process alone is not payment/email acceptance. Keep production promotion blocked until these live checks and the confirmed staging student login pass.

Rollback: suspend only newly created staging workers and the scheduler. Leave the staging/production web services, databases, existing monitoring worker and broker contents unchanged.
