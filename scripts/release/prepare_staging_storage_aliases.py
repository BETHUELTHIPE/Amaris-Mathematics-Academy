"""Copy authenticated staging S3 credentials to the legacy runtime aliases.

Only the fixed staging service is writable. No deployment is triggered here.
Secret values remain inside the protected runner and Render.
"""

import json
import os
import urllib.request

import boto3
import psycopg
from botocore.config import Config
from psycopg.rows import dict_row

from verify_render_finance_preflight import NoRedirect, api_get, service_env
from verify_supplied_staging_connection import ENDPOINT, STAGE, first
from verify_staging_database_isolation import (
    is_dedicated_supabase_staging_dsn,
    validate_dedicated_supabase_facts,
)

BUCKETS = ("amaris-staging-admin", "amaris-staging-students")


def prepare():
    service = api_get(f"services/{STAGE}")
    if service.get("ownerId") != "tea-csppi8l6l47c73dk9c90" or service.get("branch") != "staging":
        raise RuntimeError("Unexpected staging service identity")
    values = service_env(STAGE)
    dsn = values.get("STAGING_DATABASE_URL", "")
    if not is_dedicated_supabase_staging_dsn(dsn):
        raise RuntimeError("Database is not the dedicated staging project")
    with psycopg.connect(dsn, sslmode="require", connect_timeout=12, row_factory=dict_row) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        facts = conn.execute("SELECT current_database() AS database_name, current_user AS database_role, current_schema() AS schema_name").fetchone()
        if not validate_dedicated_supabase_facts(facts):
            raise RuntimeError("Unexpected staging database identity")
    access = first(values, "SUPABASE_S3_ACCESS_KEY_ID", "SUPABASE_STORAGE_S3_ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID")
    secret = first(values, "SUPABASE_S3_SECRET_ACCESS_KEY", "SUPABASE_STORAGE_S3_SECRET_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY")
    if not access or not secret:
        raise RuntimeError("Missing staging credentials")
    client = boto3.client("s3", endpoint_url=ENDPOINT, region_name="eu-west-1",
        aws_access_key_id=access, aws_secret_access_key=secret,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
            retries={"max_attempts": 1}, connect_timeout=10, read_timeout=10))
    for bucket in BUCKETS:
        client.head_bucket(Bucket=bucket)
    updates = {"AWS_ACCESS_KEY_ID": access, "AWS_SECRET_ACCESS_KEY": secret,
        "SUPABASE_S3_ACCESS_KEY_ID": access, "SUPABASE_S3_SECRET_ACCESS_KEY": secret,
        "DATABASE_URL": dsn, "DATABASE_SSL_REQUIRED": "true"}
    changed = 0
    for key, value in updates.items():
        if values.get(key) == value:
            continue
        request = urllib.request.Request(
            f"https://api.render.com/v1/services/{STAGE}/env-vars/{key}",
            data=json.dumps({"value": value}).encode(), method="PUT",
            headers={"Authorization": "Bearer " + os.environ["RENDER_API_KEY"],
                "Content-Type": "application/json", "Accept": "application/json"})
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=25) as response:
            if response.status != 200:
                raise RuntimeError("Staging alias update failed")
        changed += 1
    saved = service_env(STAGE)
    if any(saved.get(key) != value for key, value in updates.items()):
        raise RuntimeError("Staging alias verification failed")
    print(json.dumps({"staging_buckets_accessible": list(BUCKETS),
        "legacy_storage_aliases_verified": True, "changed_key_count": changed,
        "deployment_triggered": False}), flush=True)


if __name__ == "__main__":
    try:
        prepare()
    except Exception:
        print("BLOCKED: staging storage preparation failed; no secret values logged.", flush=True)
        raise SystemExit(1) from None
