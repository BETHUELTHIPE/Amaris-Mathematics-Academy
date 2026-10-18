"""Activate the tested backend in the dedicated staging project only."""

import json
import os
import urllib.error
import urllib.request
import uuid

import boto3
import psycopg
from botocore.config import Config
from psycopg.rows import dict_row

from deploy_tutor_finance_staging import ACTIVE, deploy, render, wait_checks
from prepare_staging_storage_aliases import BUCKETS, prepare
from verify_render_finance_preflight import NoRedirect, service_env
from verify_staging_database_isolation import (
    is_dedicated_supabase_staging_dsn,
    validate_dedicated_staging_bindings,
)
from verify_supplied_staging_connection import ENDPOINT, STAGE

SHA = "af8709ce7549bff6760512aaa24bdbb718d17e34"
PROJECT = "atyhhjwwxgzeurnwayay"
BASE = "https://amaris-mathematics-academy-staging.onrender.com"


def settings_for(values, public_key):
    if not public_key.startswith("sb_publishable_"):
        raise RuntimeError("A modern staging publishable key is required")
    if not is_dedicated_supabase_staging_dsn(values.get("STAGING_DATABASE_URL", "")):
        raise RuntimeError("Dedicated staging connection required")
    return {
        "DATABASE_URL": values["STAGING_DATABASE_URL"],
        "DATABASE_SSL_REQUIRED": "true", "DATABASE_SCHEMA": "public",
        "SUPABASE_DATABASE_REQUIRED": "true", "SUPABASE_PROJECT_REF": PROJECT,
        "SUPABASE_URL": f"https://{PROJECT}.supabase.co",
        "SUPABASE_PUBLISHABLE_KEY": public_key,
        "SUPABASE_S3_ENDPOINT_URL": ENDPOINT,
        "SUPABASE_STORAGE_S3_ENDPOINT": ENDPOINT, "AWS_S3_ENDPOINT_URL": ENDPOINT,
        "SUPABASE_S3_REGION": "eu-west-1", "AWS_S3_REGION_NAME": "eu-west-1",
        "AWS_S3_ADDRESSING_STYLE": "path",
        "SUPABASE_S3_ADMIN_BUCKET": BUCKETS[0], "SUPABASE_STORAGE_BUCKET_NAME": BUCKETS[0],
        "CMS_STORAGE_BUCKET_NAME": BUCKETS[0], "AWS_STORAGE_BUCKET_NAME": BUCKETS[0],
        "SUPABASE_S3_STUDENT_BUCKET": BUCKETS[1],
        "SUPABASE_STUDENT_DOCUMENTS_BUCKET_NAME": BUCKETS[1], "STUDENT_STORAGE_BUCKET_NAME": BUCKETS[1],
        "PAYFAST_MODE": "sandbox", "PAYFAST_ENV": "sandbox",
        "DJANGO_CACHE_KEY_PREFIX": "amaris-dedicated-staging",
        "DJANGO_PUBLIC_CACHE_KEY_PREFIX": "amaris-dedicated-staging-public",
        "DJANGO_DEBUG": "false",
    }


def storage_smoke(values):
    client = boto3.client("s3", endpoint_url=ENDPOINT, region_name="eu-west-1",
        aws_access_key_id=values["AWS_ACCESS_KEY_ID"], aws_secret_access_key=values["AWS_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
            retries={"max_attempts": 1}, connect_timeout=10, read_timeout=15))
    payload = b"Amaris synthetic staging storage verification. No personal data."
    for bucket in BUCKETS:
        key = "_verification/" + uuid.uuid4().hex + ".txt"
        try:
            client.put_object(Bucket=bucket, Key=key, Body=payload, ContentType="text/plain", CacheControl="private, no-store")
            signed = client.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=60)
            with urllib.request.build_opener(NoRedirect()).open(signed, timeout=20) as response:
                if response.read() != payload:
                    raise RuntimeError("Signed storage download mismatch")
            public_url = f"https://{PROJECT}.supabase.co/storage/v1/object/public/{bucket}/{key}"
            try:
                with urllib.request.build_opener(NoRedirect()).open(public_url, timeout=20):
                    raise RuntimeError("Private bucket allowed anonymous download")
            except urllib.error.HTTPError as exc:
                if exc.code not in (400, 401, 403, 404):
                    raise
        finally:
            client.delete_object(Bucket=bucket, Key=key)
        print(json.dumps({"bucket": bucket, "upload": True, "signed_download": True,
            "anonymous_download_denied": True, "synthetic_object_deleted": True}), flush=True)


def main():
    service = render(f"services/{STAGE}")
    if service.get("ownerId") != "tea-csppi8l6l47c73dk9c90" or service.get("branch") != "staging":
        raise RuntimeError("Unexpected staging target")
    if any(row.get("deploy", row).get("status") in ACTIVE
            for row in render(f"services/{STAGE}/deploys?limit=5")):
        raise RuntimeError("Another staging deploy is active")
    wait_checks(SHA, {"Python quality and Django checks", "PayFast sandbox and idempotency tests",
        "Repository secret scan", "Dependency vulnerability gates", "Responsive browser E2E",
        "Frontend, accessibility, Lighthouse, and SBOM"})
    prepare()
    values = service_env(STAGE)
    desired = settings_for(values, os.environ["STAGING_PUBLISHABLE_KEY"])
    if not validate_dedicated_staging_bindings(desired):
        raise RuntimeError("Staging integration binding check failed")
    # Targeted save-only updates preserve all unrelated configuration. The MCP
    # env mutation auto-deploys the old branch, whose migrations differ from SHA.
    for key, value in desired.items():
        if values.get(key) != value:
            render(f"services/{STAGE}/env-vars/{key}", "PUT", {"value": value})
    saved = service_env(STAGE)
    if any(saved.get(key) != value for key, value in desired.items()):
        raise RuntimeError("Saved staging configuration verification failed")
    storage_smoke(saved)
    deploy(STAGE, SHA)
    for path in ("/health/live/", "/health/ready/", "/health/version/", "/api/v1/courses/"):
        with urllib.request.build_opener(NoRedirect()).open(BASE + path, timeout=30) as response:
            body = json.load(response)
            if path == "/health/version/" and body.get("git_sha") != SHA:
                raise RuntimeError("Unexpected running staging SHA")
        print("PASS staging HTTP 200:", path, flush=True)
    with psycopg.connect(saved["DATABASE_URL"], sslmode="require", connect_timeout=12, row_factory=dict_row) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        migrations = conn.execute("SELECT name FROM django_migrations WHERE app='content' ORDER BY name").fetchall()
    print(json.dumps({"staging_content_migrations": [row["name"] for row in migrations],
        "staging_release_sha": SHA, "production_changed_by_this_job": False}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("BLOCKED: dedicated staging activation failed; inspect redacted deployment logs. Production was not changed.", flush=True)
        raise SystemExit(1) from None
