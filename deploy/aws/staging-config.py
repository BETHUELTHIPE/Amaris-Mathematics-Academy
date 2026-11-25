"""Write private runtime settings for the dedicated Amaris AWS staging project."""

import argparse
import ipaddress
import json
import os
import secrets
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT = "atyhhjwwxgzeurnwayay"
SUPABASE_URL = f"https://{PROJECT}.supabase.co"
RENDER_SERVICE = "srv-dam2iivcgkoc7383tq50"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def read_render_staging():
    request = urllib.request.Request(
        f"https://api.render.com/v1/services/{RENDER_SERVICE}/env-vars?limit=100",
        headers={"Authorization": f"Bearer {os.environ['RENDER_API_KEY']}"},
    )
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=15) as response:
        records = json.loads(response.read(1024 * 1024))
    return {record["envVar"]["key"]: record["envVar"]["value"] for record in records}


def validate_database(render):
    if render["SUPABASE_URL"].rstrip("/") != SUPABASE_URL:
        raise ValueError("Unexpected staging Auth project.")
    dsn = urllib.parse.urlsplit(render["DATABASE_URL"])
    host = dsn.hostname or ""
    user = urllib.parse.unquote(dsn.username or "")
    direct = host == f"db.{PROJECT}.supabase.co" and user == "postgres"
    pooled = host.endswith(".pooler.supabase.com") and user == f"postgres.{PROJECT}"
    if dsn.scheme not in {"postgres", "postgresql"} or not (direct or pooled):
        raise ValueError("Unexpected staging database project.")
    if render.get("DATABASE_SCHEMA", "public") != "public":
        raise ValueError("Unexpected staging database schema.")


def store_settings(path, values):
    lines = []
    for key, value in values.items():
        if not isinstance(value, str) or any(character in value for character in ('\n', '\r', '\x00')):
            raise ValueError(f"Invalid value for {key}.")
        lines.append(f"{key}={value}\n")
    payload = "".join(lines).encode()
    if len(payload) > 4096:
        raise ValueError("Staging configuration exceeds the standard SecureString parameter size.")
    with path.open("xb") as stream:
        stream.write(payload)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("address", type=ipaddress.IPv4Address)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    if not args.address.is_global:
        parser.error("An AWS public IPv4 address is required.")
    os.umask(0o077)
    try:
        render = read_render_staging()
    except (OSError, KeyError, TypeError, ValueError):
        raise SystemExit("Unable to read the Render staging configuration.") from None
    try:
        validate_database(render)
    except (KeyError, ValueError):
        raise SystemExit("The staging database isolation check failed.") from None

    address = str(args.address)
    site = f"https://{address}"
    key_file = args.directory / "django-key"
    django_secret = key_file.read_text().strip() if key_file.is_file() else secrets.token_urlsafe(64)
    publishable_key = os.environ.get("STAGING_SUPABASE_PUBLISHABLE_KEY") or render["SUPABASE_PUBLISHABLE_KEY"]
    frontend = {
        "SITE_URL": site,
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_PUBLISHABLE_KEY": publishable_key,
        "CMS_API_URL": "http://amaris-gateway:8080/api/v1",
    }
    backend = {
        "DJANGO_DEBUG": "false",
        "DJANGO_SECRET_KEY": django_secret,
        "DJANGO_ALLOWED_HOSTS": address,
        "DJANGO_CSRF_TRUSTED_ORIGINS": site,
        "CORS_ALLOWED_ORIGINS": site,
        "SERVICE_ROLE": "web",
        "PUBLIC_SITE_URL": site,
        "PUBLIC_API_URL": site,
        "DATABASE_URL": render["DATABASE_URL"],
        "DATABASE_SCHEMA": "public",
        "DATABASE_SSL_REQUIRED": "true",
        "DATABASE_CONN_MAX_AGE": "60",
        "SUPABASE_DATABASE_REQUIRED": "true",
        "SUPABASE_PROJECT_REF": PROJECT,
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_PUBLISHABLE_KEY": publishable_key,
        "DJANGO_CACHE_URL": "redis://amaris-redis:6379/0",
        "DJANGO_PUBLIC_CACHE_URL": "redis://amaris-redis:6379/1",
        "CELERY_BROKER_URL": "redis://amaris-redis:6379/2",
        "CELERY_RESULT_BACKEND": "redis://amaris-redis:6379/3",
        "WEB_CONCURRENCY": "2",
        "PAYFAST_MODE": "sandbox",
        "PAYFAST_NOTIFY_URL": f"{site}/api/v1/payfast/itn/",
        "PAYSTACK_ENABLED": "false",
        "AI_ENQUIRY_AUTOREPLY_ENABLED": "false",
        "RELEASE_GIT_SHA": os.environ["BACKEND_SHA"],
        "EMAIL_BACKEND": "django.core.mail.backends.dummy.EmailBackend",
    }
    for suffix in ("MERCHANT_ID", "MERCHANT_KEY", "PASSPHRASE"):
        backend[f"PAYFAST_{suffix}"] = os.environ[f"PAYFAST_SANDBOX_{suffix}"]
    storage = {key: render.get(key, "") for key in (
        "SUPABASE_S3_ENDPOINT_URL", "SUPABASE_S3_ACCESS_KEY_ID", "SUPABASE_S3_SECRET_ACCESS_KEY",
        "SUPABASE_S3_ADMIN_BUCKET", "SUPABASE_S3_STUDENT_BUCKET", "SUPABASE_S3_REGION",
    )}
    endpoint = urllib.parse.urlsplit(storage["SUPABASE_S3_ENDPOINT_URL"])
    if (
        endpoint.scheme == "https"
        and endpoint.hostname in {f"{PROJECT}.supabase.co", f"{PROJECT}.storage.supabase.co"}
        and all(storage.values())
    ):
        backend.update(storage, SUPABASE_S3_REQUIRED="true")
    store_settings(args.directory / "backend.env", backend)
    store_settings(args.directory / "frontend.env", frontend)
    print("Isolated staging runtime settings generated.")
    print(f"Private staging storage {'configured' if 'SUPABASE_S3_REQUIRED' in backend else 'needs verification'}.")


if __name__ == "__main__":
    main()
