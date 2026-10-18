# Dedicated staging activation, 19 October 2026 (SAST)

Backend service: `srv-dam2iivcgkoc7383tq50` in the existing confirmed Render workspace.
Supabase project: `atyhhjwwxgzeurnwayay`.
Native Python deploy: `dep-dbakpcnbtjjs73fiau30`.
Application revision: `af8709ce7549bff6760512aaa24bdbb718d17e34` (PR #272).

## Observed results

- Saved staging pooler credentials authenticated over TLS, with database `postgres`, role `postgres`, schema `public`, in a read-only check.
- Copied the verified connection to active `DATABASE_URL` without exposing it. Aligned legacy AWS storage aliases with the authenticated staging S3 credentials.
- Configured backend Auth and Storage for the dedicated staging project, modern publishable key, region `eu-west-1`, and separate private admin/student buckets.
- Both `amaris-staging-admin` and `amaris-staging-students` passed synthetic upload, signed download with exact payload comparison, anonymous download denial, and object deletion checks. No personal data was uploaded.
- Exact application SHA passed its applicable CI checks before deployment. Four deployment safety tests also passed locally and in the deployment job.
- Django migrations through `content.0014_announcement_media` completed on the initially empty dedicated database. The server's own staging isolation guard ran before migrations.
- Render reported the exact candidate live. `/health/live/`, `/health/ready/`, `/health/version/`, and `/api/v1/courses/` returned HTTP 200 from the runner. A separate external check confirmed ready, exact version, and an empty course catalogue after database hardening.
- Post-migration security review found 33 Django tables without RLS and with browser-role grants. Supabase migration `20261018225006_protect_dedicated_staging_django_tables` enabled RLS and revoked direct browser access across all 45 Django tables; corresponding sequence access and future default table/sequence grants were also revoked. Independent checks confirmed zero Django tables without RLS and zero readable by `anon` or `authenticated`.
- Security advisor after hardening returned only intentional INFO notices for RLS tables with no policies. Django's backend role retains access; Data API browser roles do not need direct application table access.
- Production backend remained on `eafb37db6cfb20a9bf84a0ec4698b5e6af10fae4`; no production service or database was mutated.

Deployment evidence: https://github.com/BETHUELTHIPE/Amaris-Mathematics-Academy/actions/runs/39173766709

## Release scope and remaining acceptance

This repairs backend staging database/storage activation and basic HTTP health. It does not establish production performance improvement or full authenticated booking/payment/email acceptance. No real payments or student messages were sent. Staging PayFast mode is explicitly sandbox.

The configured `staging` branch still contains an older divergent application migration history. The activation job pauses **staging backend** commit auto-deployment to protect the pinned candidate; production auto-deployment is unchanged. Continue deploying exact tested revisions. Reconcile the staging branch's migrations before re-enabling commit auto-deployment; do not redeploy its old tip against this database.

The hardening SQL was created using the Supabase CLI and aligned to the actual provider-generated applied migration version. It applies to the dedicated staging project; it is not evidence of a production migration or production backup.
