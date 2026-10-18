"""Read actual Render bindings without logging credentials or changing services."""

import json
import os
import sys
from urllib.parse import urlsplit

from verify_render_finance_preflight import service_env
from verify_staging_database_isolation import is_isolated_render_staging_dsn

STAGE = "srv-dam2iivcgkoc7383tq50"
PROD = "srv-dapn6b3tqb8s73d3r7n0"
STAGE_PROJECT = "atyhhjwwxgzeurnwayay"
PROD_PROJECT = "epkcuseloinygkakxxdu"


def project_in_url(value, project):
    parsed = urlsplit(value)
    return project in ((parsed.hostname or "") + (parsed.username or ""))


def main():
    try:
        stage, prod = service_env(STAGE), service_env(PROD)
        dsn = stage.get("DATABASE_URL", "")
        report = {
            "stage_database_directly_set": bool(dsn),
            "stage_database_matches_requested_supabase": project_in_url(dsn, STAGE_PROJECT),
            "stage_database_matches_old_isolated_render": is_isolated_render_staging_dsn(dsn),
            "stage_database_references_production": project_in_url(dsn, PROD_PROJECT),
            "stage_database_equals_production": bool(dsn and dsn == prod.get("DATABASE_URL")),
            "stage_auth_matches_requested_supabase": project_in_url(stage.get("SUPABASE_URL", ""), STAGE_PROJECT),
            "stage_auth_references_production": project_in_url(stage.get("SUPABASE_URL", ""), PROD_PROJECT),
            "stage_storage_references_production": any(
                project_in_url(stage.get(key, ""), PROD_PROJECT)
                for key in ("SUPABASE_S3_ENDPOINT_URL", "SUPABASE_STORAGE_S3_ENDPOINT", "AWS_S3_ENDPOINT_URL")
            ),
        }
        print(json.dumps(report, indent=2))
        if not report["stage_database_matches_requested_supabase"]:
            print("BLOCKED: actual staging service does not use the requested staging Supabase project.")
            return 1
        if report["stage_database_references_production"] or report["stage_database_equals_production"]:
            print("BLOCKED: staging database may reference production.")
            return 1
        if report["stage_auth_references_production"] or report["stage_storage_references_production"]:
            print("BLOCKED: staging auth or storage references production.")
            return 1
        print("PASS: directly configured staging service bindings are separate from production.")
        print("The candidate runtime must independently validate its effective connection before migrations.")
        return 0
    except Exception:
        # Never echo provider errors, URLs, environment values or traceback locals.
        print("BLOCKED: could not inspect actual Render bindings safely.", file=sys.stderr)
        return 1
    finally:
        os.environ.pop("STAGING_DATABASE_URL", None)


if __name__ == "__main__":
    raise SystemExit(main())
