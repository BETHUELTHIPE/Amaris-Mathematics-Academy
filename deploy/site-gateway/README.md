# One Nginx gateway for the frontend and Django backend

This opt-in Docker deployment sends every application request through one Nginx
gateway. It keeps the frontend and backend as separately versioned images.
It is a deployment alternative to the existing backend-only Compose proxy,
not an additional proxy to start inside that Compose project.

## Route ownership

| Public path | Application |
|---|---|
| `/`, course pages, login/auth callbacks, dashboards and tutor pages | Frontend |
| `/api/auth-state`, `/api/tutor-applications`, `/api/video-requests`, other frontend `/api/*` | Frontend BFF |
| `/_next/*`, `/_vinext/*`, frontend public files | Frontend |
| `/api/v1/*` | Django REST APIs, uploads, signed media and payment callbacks |
| `/api/schema/*`, `/api/docs/*` | Django API documentation |
| `/admin/*`, including permission-protected Admin monitoring | Django Admin |
| `/static/*` | Django/WhiteNoise static assets |
| `/health/*` | Django health endpoints |
| `/ws/*` | Backend transport, if the application defines a WebSocket route |
| `/media/*`, `/metrics/*`, direct `/monitoring/*` | Denied; use authorized application endpoints |
| `/nginx-health/live/` | Gateway-only liveness; not whole-application readiness |

Bare Django namespace paths also reach Django. Boundaries are exact:
`/api/v10`, `/administrator` and `/staticish` remain frontend routes.
Frontend recovery pages `/errors/<code>` remain frontend routes; upstream
Django error responses are passed through unchanged. Frontend readiness remains
available directly on its private port for the container health check.

Do not route all of `/api/` to Django: frontend BFF endpoints own authentication,
student/tutor file forwarding and other server operations. The original URI,
query string, request body, cookies, Authorization, Origin and response
Set-Cookie/Cache-Control/Vary headers are retained. Automatic request replay stays
off. Shared caching is restricted to the public-content policy below. Streaming and protocol upgrades are forwarded for both
pools; this does not create an application WebSocket feature.

Supabase Auth, private Storage signed downloads and third-party media keep their
existing external HTTPS endpoints. No bucket is made public or mounted as a
public filesystem. Direct local private-media access is denied.

## HTTPS and trusted ingress

The gateway HTTP listener is bound to host loopback by default. It MUST be
behind a trusted HTTPS terminator that enforces HTTPS, supplies the original Host,
sanitizes forwarding headers, and reaches this listener over a protected hop.
Do not publish port 8080 directly on a public interface. Nginx deliberately sets
X-Forwarded-Proto=https and port 443 for the applications; it does not trust a
browser-supplied scheme. This configuration does not obtain a certificate or
configure DNS.

Set only the real TLS ingress source CIDRs in `trusted-proxies.conf`. On a Docker
host, inspect the source address seen inside the gateway: host-loopback published
traffic can arrive from the bridge gateway. Never trust every source or an
unvalidated forwarding chain. Until configured, the conservative default retains
the proxy peer address. Verify client IP/rate-limit behavior before production.

Backend and frontend ports are not published. Cookies and authorization checks
remain the applications' responsibility; Nginx never grants student/tutor/admin
access. Private responses are not stored in a shared proxy cache or response
temporary file. Public-cache bypasses use the original unbuffered proxy path. Requests stream upstream, retaining each form's existing size
validation. The 1025 MiB transport ceiling does not grant a larger upload quota.

## Build the right frontend revision

The backend branch contains an older frontend. Do not build the website from that
copy or merge the deployment branches together. Check out each reviewed source
revision separately. The build recipe is:

```sh
docker build -f /path/to/backend-checkout/deploy/site-gateway/Frontend.Dockerfile \
  --build-arg FRONTEND_REVISION=<reviewed-frontend-sha> \
  -t amaris-frontend:<reviewed-frontend-sha> /path/to/frontend-checkout
```

Use a clean frontend checkout, and keep the Dockerfile-specific ignore file next
to the Dockerfile. The image explicitly copies source directories, excludes root
environment files, runs the production Node build with synthetic identities
disabled, and starts the resulting server as the nonroot Node user. It neither
installs credentials nor runs migrations. Runtime public/auth/recovery settings
must match the existing reviewed frontend configuration.

Build the backend from its independently reviewed revision using its existing
Dockerfile. In this topology Compose starts Gunicorn directly; the existing
Django/WhiteNoise middleware serves backend static files, collected per container
by the image entrypoint. It does not share a writable static volume between
replicas or start a second same-container Nginx.

## Deployment configuration

Provide these non-secret deployment selectors through your deployment environment:

| Variable | Required value |
|---|---|
| AMARIS_BACKEND_IMAGE | Reviewed immutable backend image, preferably registry digest |
| AMARIS_FRONTEND_IMAGE | Reviewed immutable frontend image, preferably registry digest |
| AMARIS_BACKEND_ENV_FILE | Private backend environment-file path on the deployment host |
| AMARIS_FRONTEND_ENV_FILE | Private frontend environment-file path on the deployment host |
| AMARIS_PUBLIC_ORIGIN | Canonical HTTPS site origin, without a trailing slash |
| AMARIS_GATEWAY_PORT | Loopback HTTP listener, default 8080 |

Do not put secret values in this repository. Keep the intended database, Redis,
storage buckets and mail settings in the private backend environment. Set
PUBLIC_SITE_URL and PUBLIC_API_URL to the canonical HTTPS origin; review
DJANGO_ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, secure cookies and trusted proxy
settings for that origin. Both applications need the correct Supabase project
and stable auth/action/recovery signing settings shared across their replicas.

The frontend CMS_API_URL uses the same public HTTPS origin plus /api/v1.
The private bridge permits outbound connections because the applications still
need Supabase and other authorized providers. Check that this public-origin
server-to-server route is reachable from the frontend container; it returns
through Nginx to Django and preserves correct public absolute URLs.

The Compose file creates no database, broker, workers or scheduler. Reuse the
intended existing external services and dedicated notification worker/Beat
processes; colocated notification processes are disabled on backend replicas.
Run reviewed migrations once with the existing release procedure before serving
traffic. Budget database/Redis connections, memory and rolling-release overlap.

Review the rendered configuration before any start:

```sh
docker compose -f deploy/site-gateway/compose.yml config --quiet
```

After release authorization, backups/rollback checks and staging acceptance on
the intended Docker host, start this alternative topology. Its default is one
replica per application. The explicit multi-replica form is:

```sh
docker compose -f deploy/site-gateway/compose.yml up -d \
  --scale backend=2 --scale frontend=2
```

Only the gateway is published. Each pool uses least-active-connection balancing
and Docker DNS discovery. Failed in-flight requests can return an error; they
are not retried on a different replica. Later requests use reachable peers.
Choose instance counts after measurement; this is not a concurrency guarantee.
Paid hosting/instance changes need their own reviewed rollout.

## Verification and production boundary

```sh
python backend/tests/site_gateway_smoke.py
python backend/tests/site_gateway_smoke.py --real-frontend
```

The first harness uses real Nginx and two disposable synthetic replicas per
application: route boundaries, queries, binary uploads, cookies/auth forwarding,
private paths, interrupted POST replay prevention, streaming, WebSocket
handshakes and replacement discovery. The second uses the actual production Node image and actual Django/Gunicorn
code with a disposable SQLite database, local-only mail backend and no live
Supabase credentials. It checks public SSR pages, a built JS asset, frontend API
routing, anonymous dashboard denial, Django course API/Admin login/CSRF/static
CSS and anonymous student API denial. The Django fixture image is only a narrow
HTTP acceptance image; it does not replace the separately built/scanned backend
release image. The frontend has no CMS_API_URL binding in this isolated run;
public HTTPS/CMS hairpin acceptance remains a staging gate. CI builds the pinned frontend source fa28c343dba6c4e23510ba69faf2a6c5a8c42877
separately from this backend branch. Update the pin when reviewing a new frontend
release. These checks do not verify genuine payments, real account access or
production load capacity.

Before launch, verify real staged Django Admin/static files, frontend SSR and
assets, authenticated student/tutor/admin paths, Supabase callbacks and private
uploads/downloads, frontend server actions, CMS hairpin connectivity, true client
IPs, two-application readiness, and a genuine sandbox payment/invoice/notification
journey through the public HTTPS gateway. Keep exact image digests and the prior
DNS/runtime configuration for application rollback; never reverse payment data
to roll back a proxy change.

Read-only Render inspection on 12 November 2026 still showed native Python
backend and native Node frontend services, both suspended. Render does not apply
this Compose file to those native services. No hosted runtime, billing, DNS,
paid resource or production route was changed by preparing this configuration.

## Public caching and speed

Both frontend and backend retain independently balanced pools with Docker DNS
replacement discovery. Upstream keep-alive pools are bounded at 32 idle
connections per worker/pool, with a four-second idle timeout below Gunicorn's
five-second timeout. TCP keep-alive, sendfile and bounded connection reuse reduce
connection churn without changing the application worker or database budgets.

The shared cache accepts anonymous GET/HEAD requests only on a strict allowlist:
frontend home/about/contact/course pages, frontend compiled assets, Django
static assets and Django public bootstrap/course endpoints. The origin must
explicitly return `Cache-Control: public`; its expiration, privacy and Vary
headers remain authoritative. A response setting cookies, returning an error,
using `Vary: *`, or declaring private/no-store is never stored. There is no
stale-content serving or background refresh. Privacy changes and content edits
must account for the upstream public TTL; do not put account-specific content
behind a public response header. Fingerprinted asset TTLs remain origin-owned.

Any Cookie, Authorization, query string (including signatures), write method,
Range, upgrade, RSC/Next navigation/action header, client cache-control or pragma
bypasses shared caching. Auth, student/tutor dashboards, BFF APIs, payments,
forms and private/signed downloads are outside the allowlist. The internal
uncached route retains streaming and byte-exact request bodies. Existing
private-file/metrics/monitoring path denials remain unchanged.

`X-Amaris-Cache` reports MISS/HIT/EXPIRED for eligible public requests and OFF
for uncached routes. Cache locks coalesce simultaneous anonymous cold reads.
The transient disk cache is capped at 128 MiB with a 4 MiB shared index and
10-minute inactivity cleanup; container replacement drops it. Do not mount it
as durable private storage. The cache can temporarily exceed its size target
between manager cleanup runs, so retain host disk headroom.

Gzip at level four is enabled for eligible static CSS/JavaScript/JSON/SVG/Wasm
responses over 1 KiB, with Vary negotiation. Dynamic HTML and private responses
keep gateway compression disabled; this avoids compressing reflected secrets
or buffering interactive streams. Origins may retain their existing safe
compression policies.

The updated isolated acceptance harness measures eight origin/cache reads per
pool with a deliberate 40 ms synthetic origin delay. Its timings demonstrate
proxy overhead and cache behavior only, not real site latency or capacity.
It also verifies expiry, simultaneous cold-read coalescing, cache poisoning
protection, cookie/auth/query/RSC bypass, errors, Set-Cookie, Vary and gzip/plain
negotiation. Existing routing, streaming, WebSocket, no-write-replay and replica
replacement checks remain mandatory, followed by actual frontend/Django checks.

This change prepares a Docker gateway; native Render services do not use this
Compose configuration. Production speed, availability and traffic capacity
remain unverified until hosting is restored, an authorized cutover is made and
real staging/production measurements pass. No paid service or instance changes
are made by preparing this configuration. Roll back by restoring the previous
gateway configuration/image and recreating the gateway; no database rollback or
file migration is involved.
