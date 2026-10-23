# Notification worker and Beat activation

This infrastructure-only release adds a notification queue consumer and one
Beat scheduler inside the existing single Render Standard Django instance.
It uses the existing private broker. It creates no paid resources and makes
no model, migration, booking, payment, recipient or student-site changes.

The dependency preflight requires the already-deployed content migration
`0016_separate_location_fields`, PostgreSQL, the configured Redis broker,
notification task routing and authenticated SMTP. The separate tutor/admin
notification feature in PR #336 still requires migration 0017 and its own
payment/email acceptance; this activation does not release that feature.

Set `AMARIS_COLOCATE_NOTIFICATIONS=true` on the existing web service after
deploying this code. Gunicorn supervises a notification worker with concurrency
one and a notifications-only Beat scheduler. A private Redis lease coordinates
Beat during rolling deployments. Preflight failures leave the website available
and retry with backoff. Existing notifications in the database can be delivered
after activation. No new synthetic student or payment should be created in
production for this release.

Verify both process startup logs, Celery ready/heartbeat, Beat publication and
successful notification task processing. A healthy web endpoint alone does not
prove the worker is running. SMTP authentication does not prove inbox receipt.

Production rollback: set `AMARIS_COLOCATE_NOTIFICATIONS=false` and redeploy the
existing service. There are no new migrations or stored-data transformations.
The previous application SHA is `1401bb0e20467aa345bc909e30b35d227cd374da`.
Retained production backup/restore evidence remains NOT VERIFIED; the user
authorized worker/Beat activation, and this schema-neutral release uses the
existing approved low-risk release policy. It does not constitute general
production-readiness or payment/email inbox acceptance.
