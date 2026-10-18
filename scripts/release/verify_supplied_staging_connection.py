"""Read-only verification of the new staging credentials; never print secrets."""

import json
import os
import sys

import boto3
import psycopg
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from psycopg.rows import dict_row

from verify_render_finance_preflight import service_env
from verify_staging_database_isolation import (
    is_dedicated_supabase_staging_dsn,
    validate_dedicated_supabase_facts,
)

STAGE = "srv-dam2iivcgkoc7383tq50"
ENDPOINT = "https://atyhhjwwxgzeurnwayay.storage.supabase.co/storage/v1/s3"


def first(values, *keys):
    return next((values.get(key, "").strip() for key in keys if values.get(key, "").strip()), "")


def check_storage(values, label):
    access = first(values, "SUPABASE_S3_ACCESS_KEY_ID", "SUPABASE_STORAGE_S3_ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID")
    secret = first(values, "SUPABASE_S3_SECRET_ACCESS_KEY", "SUPABASE_STORAGE_S3_SECRET_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY")
    if not access or not secret:
        print(json.dumps({"source": label, "staging_storage_authenticated": False, "reason": "credentials_missing"}))
        return False
    try:
        client = boto3.client("s3", endpoint_url=ENDPOINT, region_name="eu-west-1",
            aws_access_key_id=access, aws_secret_access_key=secret,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                retries={"max_attempts": 1}, connect_timeout=10, read_timeout=10))
        result = client.list_buckets()
        print(json.dumps({"source": label, "staging_storage_authenticated": True,
            "bucket_count": len(result.get("Buckets", []))}))
        return True
    except ClientError as exc:
        print(json.dumps({"source": label, "staging_storage_authenticated": False,
            "http_status": exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")}))
    except BotoCoreError:
        print(json.dumps({"source": label, "staging_storage_authenticated": False, "reason": "connection_failed"}))
    return False


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "storage-environment":
        return 0 if check_storage(os.environ, "protected-staging-secrets") else 1
    values = service_env(STAGE)
    dsn = values.get("STAGING_DATABASE_URL", "")
    if not is_dedicated_supabase_staging_dsn(dsn):
        print("BLOCKED: saved verification connection does not match the dedicated staging project.")
        return 1
    try:
        with psycopg.connect(dsn, sslmode="require", connect_timeout=12, row_factory=dict_row) as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            facts = conn.execute("SELECT current_database() AS database_name, current_user AS database_role, "
                "current_schema() AS schema_name, (SELECT count(*) FROM pg_tables WHERE schemaname='public') "
                "AS application_tables").fetchone()
        if not validate_dedicated_supabase_facts(facts):
            print("BLOCKED: database identity does not match the dedicated staging target.")
            return 1
        print(json.dumps({"staging_database_connection_verified": True,
            "tls_required": True, "read_only": True, "application_tables": facts["application_tables"]}))
    except psycopg.Error as exc:
        message = str(exc).lower()
        reason = "authentication_failed" if "password authentication failed" in message else (
            "pooler_identity_rejected" if "tenant or user not found" in message else "connection_failed")
        print(json.dumps({"staging_database_connection_verified": False, "reason": reason}))
        return 1
    check_storage(values, "render-staging-credentials")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("BLOCKED: safe read-only credential inspection could not complete.")
        raise SystemExit(1)
