import os
from uuid import uuid4

def main():
    import django
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")
    django.setup()
    from django.conf import settings
    from django.core.cache import caches
    from redis import Redis
    from amaris_cms.celery import app
    from urllib.parse import urlsplit
    assert settings.SUPABASE_PROJECT_REF == "atyhhjwwxgzeurnwayay"
    marker = "shared-valkey-canary:" + uuid4().hex
    for alias, db in (("default", 0), ("public_content", 1)):
        cache = caches[alias]
        url = settings.CACHES[alias]["LOCATION"]
        assert urlsplit(url).scheme == "rediss" and urlsplit(url).path == f"/{db}"
        raw = Redis.from_url(url, socket_connect_timeout=3, socket_timeout=3)
        key = cache.make_key(marker)
        try:
            assert raw.ping()
            cache.set(marker, "ok", timeout=30)
            assert raw.exists(key) and 0 < raw.ttl(key) <= 30
            assert cache.get(marker) == "ok"
        finally:
            raw.delete(key)
            raw.close()
        print(f"PASS Django {alias} cache uses shared TLS DB {db}", flush=True)
    assert urlsplit(app.conf.broker_url).scheme == "rediss"
    assert urlsplit(app.conf.broker_url).path == "/2"
    assert urlsplit(app.conf.result_backend).scheme == "rediss"
    assert urlsplit(app.conf.result_backend).path == "/3"
    with app.connection_for_write() as conn:
        conn.ensure_connection(max_retries=0)
    assert app.backend.client.ping()
    print("PASS Celery broker and result backend TLS connectivity; no task published or consumed", flush=True)

try:
    main()
except Exception as exc:
    print("Shared Valkey canary failed: " + type(exc).__name__, flush=True)
    raise SystemExit(1)
