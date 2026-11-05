# Booking release execution

Target: the current fully verified head of PR #119 in `BETHUELTHIPE/Amaris-Mathematics-Academy`. Do not substitute the existing old service branch heads. Production deployment is authorized by the user's request on 2026-10-07; execution remains gated on CI, backup and staging acceptance.

## Confirmed existing resources

Workspace: `tea-csppi8l6l47c73dk9c90`, Bethuel Moukangwe's Workspace, Frankfurt.

| Resource | ID | Current state |
| --- | --- | --- |
| Production backend | `srv-dapn6b3tqb8s73d3r7n0` | Python, standard, manual deploy; old production release branch |
| Live frontend | `srv-damn6d2d0e5s73d02j5g` | Node, free; old live branch |
| Staging backend | `srv-dam2iivcgkoc7383tq50` | Python, staging branch |
| Staging frontend | `srv-daqf69qd0e5s73ac62n0` | Node, staging branch |
| Production broker | `red-dapaglkja7ms73ajrkq0` | Available, starter, noeviction, persistent |
| Production cache | `red-dapagn4ja7ms73ajrpi0` | Available, starter, LRU cache |

## Worker setup

Use the existing reviewed `render.yaml`; preserve production secrets and existing database/buckets. Add the following missing services, with manual deploy, Python runtime, backend root directory and `pip install -r requirements.txt` build command. Reuse the existing broker and cache, without creating duplicates.

| Service | Plan | Start command |
| --- | --- | --- |
| amaris-production-critical-worker | standard | `celery -A amaris_cms worker --loglevel=INFO --queues=critical,default --concurrency=2 --events --hostname=critical@%h` |
| amaris-production-notification-worker | starter | `celery -A amaris_cms worker --loglevel=INFO --queues=notifications --concurrency=2 --events --hostname=notifications@%h` |
| amaris-production-beat | starter | `celery -A amaris_cms beat --loglevel=INFO --pidfile=/tmp/celerybeat.pid --schedule=/tmp/celerybeat-schedule` |

These are paid recurring services. Bind database, Django secret, storage, broker and notification SMTP values exactly as declared in `render.yaml`. Keep one scheduler instance. Verify worker startup, registered tasks, notification queue consumption and recurring beat publication in logs. A live broker alone does not verify workers.

## Staging acceptance

1. Promote the verified release to staging with isolated staging workers/scheduler and sandbox PayFast settings. Confirm the staging database is separate from the production booking/payment data.
2. Use a dedicated synthetic student and synthetic tutor slot, with an inbox controlled by the user. Never change a real student's email or payment record to facilitate a test.
3. Create an authenticated R250 checkout and complete the real PayFast sandbox browser flow. Capture the provider reference and the signed ITN accepted by the deployed verification endpoint. A mocked verifier or manually marked payment is not sandbox acceptance.
4. Verify authenticated booking status is confirmed and returns the expected tutor/time/Zoom link. Verify another student cannot read the booking or download its invoice.
5. Verify the notification worker archives a PDF in the private student bucket, the owner's download returns that PDF with private/no-store caching, and the inbox receives exactly one confirmation with the PDF attached.
6. Use a synthetic slot that enters the 30-minute reminder window. Let beat publish and the notification worker consume the reminder normally; verify the received reminder and one recorded send timestamp. Do not directly call the task to substitute for scheduler evidence.
7. Verify duplicate ITN, tampered amount, expired hold and second-student slot contention using synthetic records. No real payment is permitted.

## Production promotion

1. Require all current-head release checks to pass. Preserve the protected production environment and deployment concurrency lock.
2. Record the exact old and new Git SHA; retain old immutable images where the environment uses images. The current backend is Git/Python, so do not claim an image deployment that did not occur.
3. Verify a current Supabase backup/restore point before migration. Existing invoice migration history must be retained; no invoice tables or archive metadata are dropped or faked.
4. Promote backend, workers and scheduler together to the verified release. Apply migrations and verify both booking tables exist with RLS enabled and anonymous/authenticated Data API access revoked.
5. Check health/readiness, queue consumption, real SMTP and private storage configuration. Only then promote the live frontend source to the same release.
6. Run safe post-deploy checks: homepage, health, login, catalogue, API health, static assets, booking route and dedicated synthetic authentication. Do not perform a real payment.
7. If health or critical smoke checks fail, restore the previous application release and close new booking checkout. Preserve all payment records and reconcile callbacks; do not reverse payment migrations without a reviewed restore plan.

## Access constraint

The connected Render tools expose service reads, deploy triggers and environment updates, but no worker creation or existing-service branch/build update. No Render/GitHub CLI authentication is available in this workspace. Dashboard fallback requires user approval under the browser tool's plugin-fallback rule. Production has not been deployed during preparation.
