# Nginx, Gunicorn and Uvicorn

The Docker image's web command runs Nginx on `0.0.0.0:$PORT` (default 8000), with Gunicorn bound to loopback port 8001. Gunicorn manages the existing privacy-preserving uvicorn-worker class and opt-in notification supervisor. Nginx serves static files and buffers slow clients. Dynamic responses retain Django's authorization/cache headers. Payment POST bodies are forwarded unchanged without automatic replay. Private media and public metrics access are denied.

Compose retains its separate Nginx service and explicitly starts only Gunicorn in the web container. Background worker commands still override the image's web command. Single-container mode needs no additional hosted service.

## Deployment boundary

The inspected Render production backend is a **native Python service**, not this Docker image. Its current command continues to run Gunicorn directly. Merging this PR does not install Nginx on that service, change its runtime, resume a billing suspension or deploy anything. Select a supported Docker deployment/migration plan and pass staging acceptance before cutover; preserve the backend URL, storage bindings and PayFast callbacks.

The image runs as `amaris` on unprivileged ports; Nginx runtime files live in a private temporary directory. The supervisor validates configuration, exits if either web process dies, and drains Nginx before stopping Gunicorn. Set platform shutdown grace to **at least 100 seconds** for the 30-second proxy drain, 60-second Gunicorn drain and cleanup margin. Gunicorn retains ownership of notification shutdown. No schema migration is introduced. Retain the previous tested artifact/configuration for application rollback; do not reverse external payment/email effects. CI, backup/restore and inbox acceptance remain release gates.

## Initial settings

| Setting | Default / initial value | Purpose |
|---|---|---|
| PORT | 8000 or platform-assigned port | Nginx public listener |
| GUNICORN_UPSTREAM_PORT | 8001 | Loopback ASGI listener; must differ from PORT |
| WEB_CONCURRENCY | Derived from cgroup v2 CPU/memory, capped at 4 | Override after measurement; fallback memory budget is 1 GiB |
| UVICORN_LIMIT_CONCURRENCY | 32 per worker | Bound active work/connections; excess receives 503 |
| GUNICORN_BACKLOG | 256 | Bound pending socket queue |
| DATABASE_CONN_MAX_AGE | 0 | Release thread-local connections after ASGI requests |
| DATABASE_POOL_ENABLED | false | Opt into bounded physical PostgreSQL session reuse |
| DATABASE_POOL_MIN_SIZE | 0 | Avoid pre-opening unused sessions |
| DATABASE_POOL_MAX_SIZE | 4 per process/database alias | Bound database sessions |
| DATABASE_POOL_MAX_WAITING | 32 | Bound waiting database work |
| DATABASE_POOL_TIMEOUT | 5 seconds | Bound database queue wait |
| NGINX_TRUST_FORWARDED_PROTO | true only when RENDER=true | Preserve HTTPS from a trusted TLS terminator |

Two workers with pool size four can use eight database sessions per instance. Add every Celery/management process, instance and rolling-deployment overlap, and leave database headroom. The worker heuristic reserves 256 MiB for the proxy/master plus another 512 MiB when notifications are colocated. Unsupported cgroup layouts use fallback values; this is an initial sizing heuristic, not a memory guarantee. Measure RSS and database usage before increasing limits.

Explicitly change an existing DATABASE_CONN_MAX_AGE=600 environment value to zero before ASGI rollout. Enabling the PostgreSQL pool forces zero. SQLite never receives pool options. Pooling preserves database URL, schema, SSL enforcement and credentials. Prefer the existing Supabase session/direct connection for this persistent backend. A switch to transaction pooling requires a separate review of prepared statements, server-side cursors and session settings. Pool timeout retains existing application error behavior; admission control does not replace load testing.

Forwarded HTTPS is trusted only behind the configured platform edge; explicitly set NGINX_TRUST_FORWARDED_PROTO=true only when that edge sanitizes the header. Directly exposed HTTP deployments leave it false. Nginx neither caches private responses nor globally compresses personalized dynamic data. Static filenames revalidate after one hour. Its 1025 MiB body ceiling allows a 1 GiB file plus multipart overhead, while each form retains its own file-size validators. Large uploads require realistic staging acceptance. Single-container mode denies all /media/ paths: inventory local-only public media first and use configured storage URLs for public production assets. Private downloads retain application authorization/signed URLs.

## Verification

From backend/ with dependencies installed and Nginx available:

```sh
python manage.py collectstatic --noinput
python -m unittest tests.test_web_runtime
python -m tests.runtime_smoke
DATABASE_POOL_ENABLED=true python manage.py test tests.test_database_pool
```

The real loopback smoke harness uses a clean synthetic environment, disposable SQLite database, Django ASGI, Nginx and Gunicorn/Uvicorn. It checks readiness, static serving, private-path denial and graceful shutdown. A synthetic ASGI fixture checks POST body preservation, protected-response isolation, JSON errors, streaming, overload 503s and recovery. It never contacts a remote service, emails anyone or calls PayFast. PostgreSQL integration tests prove session reuse and the pool ceiling against CI's disposable database.

CI builds/scans the changed image and runs the existing release gates. Local smoke tests do not establish Docker-image or hosted acceptance. Run existing staging load profiles and preserve p95/p99/error thresholds; compare latency, throughput, RSS, database sessions, queue depth and restarts on the same workload. No speedup percentage, production capacity or 50,000-user claim is established.

### Observed local validation, 30 October 2026

- Python 3.13.15: full Django run completed with 248 tests, 5 skipped; no failures. The isolated PostgreSQL pool tests are among the skips.
- Black, Ruff, mypy (42 source files), migration drift and YAML parsing checks passed.
- Production and installed development dependency audits report no known vulnerabilities after updating Black and pypdf to patched releases.
- Actual local Nginx 1.24.0, Gunicorn and Uvicorn smoke acceptance passed. The restricted local runner required Nginx single-process mode; CI's separate Docker smoke check must still prove production's nonroot master/worker mode.
- Docker image build/security scan, real PostgreSQL pool integration, hosted staging acceptance and before/after performance measurements have not run for this change. Production remains unchanged.

References:

- https://docs.djangoproject.com/en/5.2/ref/databases/
- https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/uvicorn/
- https://nginx.org/en/docs/http/ngx_http_proxy_module.html
- https://supabase.com/docs/guides/database/connecting-to-postgres
