# Django, Celery and Celery Beat in staging and production

Status: implementation and provisioning preparation only. New worker compute is
not approved or purchased. The existing web, database, broker and monitoring
services are unchanged. Celery is a Python library; always-on worker and scheduler
processes still require compute.

## Concrete service plan

Both environments already have Django's Celery app, task registry, database-backed
delivery state, retries and Beat schedules. Start the following native Python
background workers from the existing Django releases. Run commands after
`cd backend`, with `exec` so Celery receives Render's termination signal.

| Environment | Process | Command |
| --- | --- | --- |
| staging | amaris-staging-critical-worker | `celery -A amaris_cms worker --loglevel=INFO --queues=critical,default --concurrency=1 --events --hostname=staging-critical-worker@%h` |
| staging | amaris-staging-notification-worker | `celery -A amaris_cms worker --loglevel=INFO --queues=notifications --concurrency=1 --events --hostname=staging-notification-worker@%h` |
| staging | amaris-staging-beat | `celery -A amaris_cms beat --loglevel=INFO --pidfile=/tmp/celerybeat.pid --schedule=/tmp/celerybeat-schedule` |
| production | amaris-production-critical-worker | `celery -A amaris_cms worker --loglevel=INFO --queues=critical,default --concurrency=1 --events --hostname=production-critical-worker@%h` |
| production | amaris-production-notification-worker | `celery -A amaris_cms worker --loglevel=INFO --queues=notifications --concurrency=1 --events --hostname=production-notification-worker@%h` |
| production | amaris-production-beat | `celery -A amaris_cms beat --loglevel=INFO --pidfile=/tmp/celerybeat.pid --schedule=/tmp/celerybeat-schedule` |

Each process uses one Frankfurt `0.5c-512mb` instance, manual deployments and a
120-second shutdown allowance. Initial estimate: US$7/month per process,
US$21/month per environment, US$42/month for both, excluding tax and usage.
This is additional to the approved monitoring budget. No new database, Redis,
disk, cron service or monitoring infrastructure is included. Initial concurrency
is conservative; this is not capacity-test evidence.

| Setting | Staging | Production |
| --- | --- | --- |
| Django source | `1b3b0c532060212578ad7e512dc1f4cf64eb8657` | `751393e8fdd4eba96cec354b013bb6654431068c` |
| Existing web service | `srv-dam2iivcgkoc7383tq50` | `srv-dapn6b3tqb8s73d3r7n0` |
| Existing broker | `red-dam2golbedkc73ae6ph0` | `red-dapaglkja7ms73ajrkq0` |
| Database/Auth/storage project | `atyhhjwwxgzeurnwayay` | `epkcuseloinygkakxxdu` |
| Queue eviction | noeviction | noeviction |
| Beat instances | exactly one | exactly one |
| Scheduler timezone | Africa/Johannesburg | Africa/Johannesburg |

The application build rejects a source SHA different from the reviewed live web
release. A later application release requires reviewing/updating these pins and
deploying compatible web/worker versions together; do not deploy newer `main`
application code over these branches. The PayFast fix in PR #322 is a separate,
unreleased change and is not activated by this infrastructure plan.

## Email and scheduling behavior

Django persists paid booking/course/video and tutor notification state. Celery
workers generate/archive invoices and deliver email through Django's SMTP email
backend. Beat periodically queues work; it does not send emails or execute the
jobs itself. Existing delivery-state checks and row locks limit duplicate
processing, while failed tasks use backoff and terminal-failure visibility.
SMTP cannot guarantee exactly-once delivery if acceptance succeeds immediately
before a process/transaction fails; verify this edge case separately.

Existing schedule intervals are retained: receipts and confirmations every 30
seconds; class reminders every 60 seconds; missing invoice archives every 120
seconds; payment reconciliation and hold expiry every 300 seconds; tutor earnings
reconciliation every 600 seconds. Class reminders select due confirmed classes
using the existing 30-minute reminder window.

Scope limitation discovered during inspection: contact-page AI enquiry replies
still use synchronous SMTP in `ContactEnquirySerializer.create`. Provisioning
these workers does not make that path asynchronous. Supabase-managed Auth email
also stays with its authentication provider. Do not claim that every email path
has moved to Celery based on this plan.

## Protected provisioning and verification

`deploy/celery/provision.py` defaults to a local plan with no network calls:

```sh
python deploy/celery/provision.py --environment staging
python deploy/celery/provision.py --environment production
python -m unittest discover -s deploy/celery -p 'test_*.py' -v
```

The dedicated GitHub workflow checks the actual task registry and queue routes
in both pinned Django releases without running tasks or sending messages. Its
one-time protected preflight reads actual Render configuration without making
any changes. It verifies the existing live source, database/Auth/storage project,
SSL, SMTP settings, non-evicting broker, queue isolation, secret allowlist and
service-name collisions before allowing any create request.

Live inspection found that production web has no SMTP host, login, app password
or real sender configured. The prepared production notification-worker plan
therefore copies only SMTP settings from the existing configured Amaris sender
in staging, restricted to the known owner-controlled Gmail sender and matching
login. It retains production's own database, Auth, storage and queue bindings.
Both preflights authenticate through Gmail TLS without submitting any email;
authentication failure blocks service creation. Neither web service's settings
are changed. Credential presence/authentication is not inbox-delivery proof.

After separate recurring-cost approval, merge the reviewed infrastructure PR
and dispatch **Django Celery staging and production services** on `main`. Select
`target=staging`, `apply=true`, `approved_monthly_usd=21`. The protected production
GitHub environment holds the existing Render API credential; its use for staging
does not change the staging resource targets. Start with staging. Repeat for
production only after staging runtime checks pass and production activation is
authorized. A read-only dispatch uses `apply=false` and incurs no new compute.

The Render connector currently cannot create background workers, so only the
reviewed GitHub provisioning operation uses the Render REST create-service API.
Use the Render connector to inspect resulting services, deployments and logs.
No API token, merchant secret, connection string, student data or SMTP password
is printed or committed. The API client cannot update, delete, deploy or resize
existing resources. Repeated/partial attempts adopt matching services and refuse
configuration drift instead of creating duplicates or overwriting secrets.

Live acceptance after creation:

1. Observe each exact-source deployment reach `live`, then inspect worker startup
   logs for its registered queues and absence of errors.
2. On an authorized shell, inspect named worker `ping` and `active_queues`. Verify
   the monitoring worker still consumes only `monitoring-verification`.
3. Observe Beat queue a due task and the correct worker complete it autonomously.
4. In staging, use only the approved synthetic student and sandbox funds. Verify
   genuine provider ITN settlement, private PDF archive, matching Gmail PDF
   attachment and automatic 30-minute reminder. Do not call tasks directly to
   substitute for scheduler/worker acceptance. Do not send to other real people.
5. Check retries, delayed/duplicate ITNs and delivery state. SMTP configuration,
   Celery startup or local file-mailbox tests alone are not Gmail delivery proof.
6. In production, confirm the deployed dependency settings and normal scheduled
   operation without making real test payments or modifying real student data.

Exactly one Beat process may run per environment. On later Beat updates, suspend
and confirm the old process has stopped before starting its replacement; ordinary
zero-downtime rolling deployment can overlap schedulers. Never use `worker -B`
or run Beat inside each web instance. Do not scale Beat above one instance.

Rollback: stop/suspend the newly created Beat first, then its new workers. Leave
web services, databases, brokers, queues and monitoring unchanged; do not purge
queued tasks. Suspending compute is a separate explicit operational step, not an
automatic destructive rollback. Record all created service/deploy IDs.

The staging free broker currently has no persistence. This plan preserves that
existing setting; recovery of broker contents after a Redis restart is not
verified. Database-backed pending notification scans provide a recovery path
for their own records, not a guarantee for every arbitrary Celery task.

References: [Django integration](https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html),
[Beat scheduling](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html),
[Render compute plans](https://render.com/docs/compute-plans),
[Render pricing](https://render.com/pricing),
[Render deployments](https://render.com/docs/deploys).
