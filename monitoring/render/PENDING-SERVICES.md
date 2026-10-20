# Missing monitoring services — approval proposal

Do not apply `pending-services.yaml` until the owner approves its additional recurring budget. This file is separate from the active Blueprint paths and defines only three missing services; it does not redefine the existing backend, Flower, exporter or databases.

| Resource | Starting configuration | Monthly base estimate (USD) |
| --- | --- | ---: |
| Private Prometheus | Docker, Frankfurt, 0.5 CPU / 512 MB, 1 GB disk | 7.25 |
| Private Grafana | Docker, Frankfurt, 0.5 CPU / 512 MB, 1 GB disk | 7.25 |
| Celery verification worker | Docker, Frankfurt, 0.5 CPU / 512 MB, concurrency 1 | 7.00 |
| Total additional | Excludes tax, usage and existing charges | 21.50 |

Pricing source: https://render.com/pricing. This is a small starting configuration, not a verified capacity guarantee. A Beat scheduler is not included.

## Safe activation sequence

1. Obtain explicit approval for the extra recurring cost. Inspect Render's deployment plan: exactly the three new service names and two one-GB disks must be added, with no replacements or database changes. The YAML passed Render's published JSON Schema; account-aware provider validation remains required.
2. Verify that `DJANGO_SECRET_KEY` and `DATABASE_URL` exist on the production backend. `fromService` references copy them within Render without exposing their values. Reuse the existing production broker. Never copy production secrets into GitHub source or terminal output.
3. Deploy the worker on the isolated `monitoring-verification` queue first. It emits real Celery events but does not consume the application's production queues. Confirm current heartbeats in Flower. No synthetic worker or fabricated healthy state is acceptable.
4. Deploy private Prometheus and Grafana. Verify Django, Flower and exporter scrape targets, real datasource samples and disk write paths. Use internal service addresses only; no public dashboard service or new domain is required.
5. Set the backend's Grafana and Prometheus origin variables only after actual services exist. Verify the authenticated superuser page, denial to ordinary staff/students, dashboard navigation and real metric freshness.
6. Before switching the worker to `critical,default,notifications`, separately verify its private-storage and SMTP configuration, task ownership/idempotency, and intended handling of the existing queue. The initial verification worker is not evidence of production task delivery.

Do not apply the full root `render.yaml` as a shortcut: it contains other production resources outside this proposal. The proposal uses manual deployment settings to avoid unexpected rollouts before approval. Disk-backed dashboard deploys interrupt those dashboards briefly. No proposed services or disks have been created.
