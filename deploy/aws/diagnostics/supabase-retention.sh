#!/usr/bin/env bash
set -euo pipefail
[[ "$1" =~ ^[a-f0-9]{32}$ && "$2" =~ ^(write|verify|clean)$ && "$3" =~ ^[a-f0-9]{32}$ ]]
task="arn:aws:ecs:eu-north-1:110156539003:task/amaris-ecs-staging/$1"
backend="$(docker ps -q --filter "label=com.amazonaws.ecs.task-arn=$task" --filter label=com.amazonaws.ecs.container-name=backend)"
[[ "$backend" =~ ^[a-f0-9]{12,64}$ ]]
docker exec -i "$backend" python - "$2" "$3" <<'PY'
import os
import sys
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

for line in os.environ.pop("AMARIS_RUNTIME_ENV", "").splitlines():
    key, sep, value = line.partition("=")
    if sep:
        os.environ[key] = value
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")
import django
django.setup()
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.db import connection, transaction

PROJECT = "atyhhjwwxgzeurnwayay"
phase, nonce = sys.argv[1:3]
db = connection.settings_dict
assert connection.vendor == "postgresql" and os.environ.get("SUPABASE_PROJECT_REF") == PROJECT
assert (db["HOST"] == f"db.{PROJECT}.supabase.co" or
        (db["HOST"].endswith(".pooler.supabase.com") and db["USER"].endswith("." + PROJECT)))
endpoint = urlsplit(settings.SUPABASE_S3_ENDPOINT_URL)
assert endpoint.scheme == "https" and endpoint.hostname == f"{PROJECT}.storage.supabase.co"

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None

http = build_opener(NoRedirect())
def check_database():
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()")
        assert cursor.fetchone() == (True,)
        cursor.execute("SELECT EXISTS(SELECT 1 FROM django_migrations)")
        assert cursor.fetchone() == (True,)
        cursor.execute("CREATE TEMP TABLE retention_smoke (value text) ON COMMIT DROP")
        cursor.execute("INSERT INTO retention_smoke VALUES (%s) RETURNING value", [nonce])
        assert cursor.fetchone() == (nonce,)
    print("Supabase PostgreSQL TLS, migration history and disposable write passed.", flush=True)

def check_file(alias, storage):
    assert storage.endpoint_url == settings.SUPABASE_S3_ENDPOINT_URL and storage.querystring_auth
    expected = f"Disposable staging storage check {nonce} {alias}".encode()
    key = f"staging-health/{nonce}/{alias}.txt"
    if phase == "write":
        assert not storage.exists(key)
        assert storage.save(key, ContentFile(expected)) == key
    elif phase == "verify":
        with storage.open(key, "rb") as response:
            assert response.read(len(expected) + 1) == expected
        url = storage.url(key, expire=90)
        parsed = urlsplit(url)
        assert parsed.scheme == "https" and parsed.hostname == endpoint.hostname
        assert parse_qs(parsed.query).get("X-Amz-Expires") == ["90"]
        with http.open(Request(url), timeout=12) as response:
            assert response.status == 200 and response.read(len(expected) + 1) == expected
        try:
            with http.open(urlunsplit(parsed._replace(query="")), timeout=12):
                raise AssertionError("Unsigned object was readable")
        except HTTPError as exc:
            assert exc.code in (400, 401, 403, 404)
    elif storage.exists(key):
        with storage.open(key, "rb") as response:
            assert response.read(len(expected) + 1) == expected
        storage.delete(key)
        assert not storage.exists(key)
    print(f"{phase} passed for {alias} using {storage.bucket_name}", flush=True)

try:
    if phase != "clean":
        check_database()
    aliases = {"default": "amaris-staging-admin", "student_private": "amaris-staging-students",
               "tutor_qualifications": None}
    for alias, bucket in aliases.items():
        storage = storages[alias]
        assert storage.bucket_name in ({bucket} if bucket else {"amaris-staging-admin", "amaris-tutor-files"})
        check_file(alias, storage)
except Exception as exc:
    # Provider exception messages can include a signed object URL.
    print(f"Supabase {phase} verification failed: {type(exc).__name__}.", file=sys.stderr)
    raise SystemExit(1) from None
finally:
    connection.close()
PY
