#!/usr/bin/env bash
set -euo pipefail

[[ "$1" =~ ^[a-f0-9]{32}$ && "$2" =~ ^(database|storage|transaction)$ ]]
arn="arn:aws:ecs:eu-north-1:110156539003:task/amaris-ecs-staging/$1"
backend="$(docker ps -q --filter "label=com.amazonaws.ecs.task-arn=$arn" --filter label=com.amazonaws.ecs.container-name=backend)"
[[ "$backend" =~ ^[a-f0-9]{12,64}$ ]] || { echo 'The staging backend container is not running yet.' >&2; exit 1; }

docker exec -i "$backend" python - "$2" <<'PY'
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, quote, urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

for item in Path("/proc/1/environ").read_bytes().split(b"\0"):
    if item:
        key, _, value = os.fsdecode(item).partition("=")
        os.environ[key] = value

PROJECT = "atyhhjwwxgzeurnwayay"
SUPABASE = f"https://{PROJECT}.supabase.co"
STORAGE_HOST = f"{PROJECT}.storage.supabase.co"


def check_database():
    from django.db import connection

    settings = connection.settings_dict
    host = settings["HOST"]
    direct = host == f"db.{PROJECT}.supabase.co"
    pooler = host.endswith(".pooler.supabase.com") and settings["USER"].endswith(f".{PROJECT}")
    assert direct or pooler, "Django database must belong to staging."
    successful = 0
    for _ in range(4):
        try:
            connection.close()
            with connection.cursor() as cursor:
                cursor.execute("select 1, to_regclass('auth.users') is not null, to_regclass('public.django_migrations') is not null")
                assert cursor.fetchone() == (1, True, True), "Database or schema check failed."
                driver = connection.connection
                if hasattr(driver, "pgconn"):
                    tls = driver.pgconn.ssl_in_use
                else:
                    tls = driver.info.ssl_in_use
                assert tls, "The connection to the configured endpoint did not use TLS."
            successful += 1
        except Exception as error:
            cause = error.__cause__ or error
            detail = str(cause).lower()
            matched = next((tag for phrase, tag in (
                ("max client", "pool client limit"), ("remaining connection slots", "database connection limit"),
                ("pool timeout", "pool timeout"), ("timed out", "connection timeout"),
                ("authentication failed", "authentication"), ("could not translate", "DNS"),
                ("connection reset", "connection reset"), ("server closed", "server closed connection"),
            ) if phrase in detail), "unclassified")
            print(f"PostgreSQL sample failure: {type(cause).__name__}, {matched}.", file=sys.stderr, flush=True)
            if isinstance(cause, AssertionError):
                print(str(cause), file=sys.stderr, flush=True)
        finally:
            connection.close()
        time.sleep(1)
    print(f"Supabase PostgreSQL over TLS: {successful}/4 new connection checks passed.", flush=True)
    return successful == 4


def check_auth():
    assert os.environ["SUPABASE_URL"].rstrip("/") == SUPABASE, "Unexpected staging Auth project."
    key = os.environ["SUPABASE_PUBLISHABLE_KEY"]
    assert key.startswith("sb_publishable_") or key.startswith("eyJ"), "Unexpected frontend key type."
    request = Request(f"{SUPABASE}/auth/v1/health", headers={"apikey": key, "Accept": "application/json"})
    with urlopen(request, timeout=10) as response:
        assert response.status == 200
    print("Live ECS configuration points to the staging Supabase Auth project, and Auth health returned 200.", flush=True)


def check_storage():
    from django.core.files.base import ContentFile
    from django.core.files.storage import storages

    for alias, expected in (("default", "amaris-staging-admin"), ("student_data", "amaris-staging-students")):
        storage = storages[alias]
        assert storage.bucket_name == expected and urlsplit(storage.endpoint_url).hostname == STORAGE_HOST
        key = f"aws-staging-smoke/{uuid4().hex}.txt"
        name = key
        data = f"Amaris isolated staging verification {uuid4().hex}".encode()
        try:
            name = storage.save(key, ContentFile(data))
            assert name == key, "Unexpected saved key."
            assert storage.exists(name), "The smoke file is missing after upload."
            with storage.open(name, "rb") as source:
                assert source.read() == data, "Django storage returned different content."
            signed = urlsplit(storage.url(name, expire=60))
            params = parse_qs(signed.query)
            assert signed.scheme == "https" and signed.hostname == STORAGE_HOST
            assert params.get("X-Amz-Expires") == ["60"] and params.get("X-Amz-Signature"), "Expected a temporary signed link."
            with urlopen(signed.geturl(), timeout=10) as response:
                assert response.read(len(data) + 1) == data, "The signed download returned different content."
            anonymous = f"{SUPABASE}/storage/v1/object/public/{expected}/{quote(name)}"
            try:
                with urlopen(anonymous, timeout=10):
                    raise AssertionError("A private smoke file was available through a public URL.")
            except HTTPError as error:
                assert error.code in {400, 401, 403, 404}, "Unexpected HTTP status for anonymous download."
        finally:
            storage.delete(name)
            assert not storage.exists(name), "The disposable smoke file was not removed."
        print(f"{expected}: Django upload/read, signed download, anonymous denial, and cleanup passed.", flush=True)


try:
    import django
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")
    django.setup()
    if sys.argv[1] == "transaction":
        from django.db import connection
        from content.models import SiteSettings

        settings = connection.settings_dict
        assert settings["HOST"].endswith(".pooler.supabase.com") and settings["USER"].endswith(f".{PROJECT}")
        settings["PORT"] = "6543"
        settings["CONN_MAX_AGE"] = 0
        settings["DISABLE_SERVER_SIDE_CURSORS"] = True
        settings["OPTIONS"]["prepare_threshold"] = None
        assert check_database()
        with connection.cursor() as cursor:
            cursor.execute("show statement_timeout")
            statement_timeout = cursor.fetchone()[0]
        assert SiteSettings.objects.values("pk").first() is not None, "The staging ORM query did not return the site settings row."
        print(f"Supavisor transaction pool passed four TLS connections and a Django ORM query. Statement timeout: {statement_timeout}.")
        raise SystemExit(0)
    if sys.argv[1] == "database":
        healthy = check_database()
        check_auth()
        raise SystemExit(0 if healthy else 1)
    check_storage()
except Exception as error:
    # Errors can include credentials, object URLs or raw provider responses.
    print(f"Supabase runtime check failed: {type(error).__name__}.", file=sys.stderr)
    if isinstance(error, HTTPError):
        print(f"Supabase returned HTTP {error.code}.", file=sys.stderr)
    if isinstance(error, AssertionError):
        print(str(error), file=sys.stderr)
    raise SystemExit(1) from None
PY
