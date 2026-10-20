# Missing monitoring services — approved Render plan

The owner explicitly resumed the previously approved USD 21.50/month plan after the temporary free-hosting pause. Apply only the three new resources in `pending-services.yaml`. The standalone alternative remains documented in `../self-hosted/README.md` for an existing Docker host.

The Render connector cannot create private services, background workers or disks. The alternative is `.github/workflows/provision-approved-monitoring.yml`, using the existing protected `RENDER_API_KEY` in the `production` environment to call Render's official API. It verifies the approved manifest hash and workspace, validates the Blueprint with Render before initial provisioning, and creates only missing resources with their disks included in the initial create request. It never modifies existing services, rotates an existing Grafana password, starts production queues, or logs credentials. Repeated runs retain matching resources; conflicting names/configuration stop the run. Keep any GitHub environment approval requirements in place.

This file is separate from the active Blueprint paths and defines only three missing services; it does not redefine the existing backend, Flower, exporter or databases. Direct API provisioning does not register a Blueprint in the Dashboard; do not later apply the same manifest as an additional deployment without first reviewing resource ownership.

| Resource | Starting configuration | Monthly base estimate (USD) |
| --- | --- | ---: |
| Private Prometheus | Docker, Frankfurt, 0.5 CPU / 512 MB, 1 GB disk | 7.25 |
| Private Grafana | Docker, Frankfurt, 0.5 CPU / 512 MB, 1 GB disk | 7.25 |
| Celery verification worker | Docker, Frankfurt, 0.5 CPU / 512 MB, concurrency 1 | 7.00 |
| Total additional | Excludes tax, usage and existing charges | 21.50 |

Pricing source: https://render.com/pricing. This is a small starting configuration, not a verified capacity guarantee. A Beat scheduler is not included.

## Safe activation sequence

1. Inspect Render's deployment plan: exactly the three new service names and two one-GB disks must be added, with no replacements or database changes. The YAML passed Render's published JSON Schema; account-aware provider validation runs before the initial API provisioning request.
2. Verify that `DJANGO_SECRET_KEY`, `DATABASE_URL` and `SUPABASE_PROJECT_REF` exist on the production backend. The worker needs the project reference to pass the app's enforced Supabase database identity check. `fromService` references copy them within Render without exposing secret values. Reuse the existing production broker. Never copy production secrets into GitHub source or terminal output.
3. Deploy the worker on the isolated `monitoring-verification` queue first. It emits real Celery events but does not consume the application's production queues. Confirm current heartbeats in Flower. No synthetic worker or fabricated healthy state is acceptable.
4. Deploy private Prometheus and Grafana. Verify Django, Flower and exporter scrape targets, real datasource samples and disk write paths. Use internal service addresses only; no public dashboard service or new domain is required.
5. Set the backend's Grafana and Prometheus origin variables only after actual services exist. Preserve existing `DJANGO_ALLOWED_HOSTS` entries and add the backend's actual private hostname, so private metric scrapes pass Django's Host validation. Verify the authenticated superuser page, denial to ordinary staff/students, dashboard navigation and real metric freshness.
6. Before switching the worker to `critical,default,notifications`, separately verify its private-storage and SMTP configuration, task ownership/idempotency, and intended handling of the existing queue. The initial verification worker is not evidence of production task delivery.

Do not apply the full root `render.yaml` as a shortcut: it contains other production resources outside this proposal. The proposal uses manual deployment settings to avoid unexpected rollouts before approval. Disk-backed dashboard deploys interrupt those dashboards briefly. No proposed services or disks have been created.
