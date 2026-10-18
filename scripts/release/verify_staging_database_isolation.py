"""Read-only gate: do not deploy Render staging unless its *actual* DB credentials are isolated.

This is deliberately an independent connection using a staging-only protected GitHub
environment secret. Never fall back to the production DATABASE_URL.
"""

from __future__ import annotations

import os
import sys
from urllib.parse import unquote, urlsplit

import psycopg
from psycopg.rows import dict_row

EXPECTED_ROLE = "amaris_staging_app"
EXPECTED_SCHEMA = "amaris_staging"
RENDER_STAGE_HOST = "dpg-dam2gj6k1f9s73e81tmg-a"
RENDER_STAGE_DATABASE = "amaris_staging_postgres"
RENDER_STAGE_ROLE = "amaris_staging_postgres_user"
SUPABASE_STAGE_REF = "atyhhjwwxgzeurnwayay"


def is_dedicated_supabase_staging_dsn(dsn: str) -> bool:
    """Accept only the user's separate staging project, never production."""
    try:
        parsed = urlsplit(dsn)
        host = (parsed.hostname or "").lower()
        user = unquote(parsed.username or "")
        direct = host == f"db.{SUPABASE_STAGE_REF}.supabase.co" and user == "postgres"
        pooled = (
            host.endswith(".pooler.supabase.com")
            and user == f"postgres.{SUPABASE_STAGE_REF}"
        )
        return bool(
            parsed.scheme in ("postgres", "postgresql")
            and (direct or pooled)
            and parsed.port in (None, 5432)
            and parsed.password
            and unquote(parsed.path).lstrip("/") == "postgres"
        )
    except ValueError:
        return False


def validate_dedicated_supabase_facts(facts):
    return bool(
        facts
        and facts["database_name"] == "postgres"
        and facts["database_role"] == "postgres"
        and facts["schema_name"] == "public"
    )


def validate_dedicated_staging_bindings(values):
    """The dedicated staging runtime must not authenticate or upload to production."""
    auth = urlsplit(values.get("SUPABASE_URL", ""))
    endpoint = next(
        (
            values.get(key, "")
            for key in (
                "SUPABASE_S3_ENDPOINT_URL",
                "SUPABASE_STORAGE_S3_ENDPOINT",
                "AWS_S3_ENDPOINT_URL",
            )
            if values.get(key, "")
        ),
        "",
    )
    storage = urlsplit(endpoint)
    return bool(
        auth.scheme == "https"
        and auth.hostname == f"{SUPABASE_STAGE_REF}.supabase.co"
        and not auth.username
        and values.get("SUPABASE_PUBLISHABLE_KEY", "").strip()
        and storage.scheme == "https"
        and storage.hostname
        in (
            f"{SUPABASE_STAGE_REF}.storage.supabase.co",
            f"{SUPABASE_STAGE_REF}.supabase.co",
        )
        and not storage.username
        and storage.path.rstrip("/") == "/storage/v1/s3"
    )


def is_isolated_render_staging_dsn(dsn: str) -> bool:
    """Allow only the existing, independently identified Render staging resource."""
    try:
        parsed = urlsplit(dsn)
        return bool(
            parsed.scheme in ("postgres", "postgresql")
            and parsed.hostname
            in (RENDER_STAGE_HOST, RENDER_STAGE_HOST + ".frankfurt-postgres.render.com")
            and parsed.port in (None, 5432)
            and unquote(parsed.username or "") == RENDER_STAGE_ROLE
            and parsed.password
            and unquote(parsed.path).lstrip("/") == RENDER_STAGE_DATABASE
        )
    except ValueError:
        return False


def validate_render_facts(facts):
    return bool(
        facts
        and facts["database_name"] == RENDER_STAGE_DATABASE
        and facts["database_role"] == RENDER_STAGE_ROLE
        and facts["schema_name"] == "public"
    )


def validate_facts(facts: dict[str, object]) -> tuple[bool, str]:
    """Fail closed if this DB connection could touch production public tables."""
    if facts["current_user"] != EXPECTED_ROLE:
        return False, "Database connection does not use the restricted staging role."
    if facts["current_schema"] != EXPECTED_SCHEMA:
        return (
            False,
            "Database connection would create Django tables outside the staging schema.",
        )
    first_path = str(facts["search_path"]).split(",")[0].strip().strip('"')
    if first_path != EXPECTED_SCHEMA:
        return (
            False,
            "The effective search path does not start with the staging schema.",
        )
    if not facts["staging_schema_exists"] or not facts["staging_schema_creatable"]:
        return (
            False,
            "The staging schema is missing or not writable by the staging role.",
        )
    if facts["public_schema_creatable"]:
        return (
            False,
            "Staging role could create database objects in production public schema.",
        )
    if facts["public_readable_tables"] or facts["public_writable_tables"]:
        return False, "Staging database role can access production public tables."
    return (
        True,
        "Restricted staging connection verified. No production table privileges.",
    )


QUERY = """
SELECT
    current_user::text AS current_user,
    current_schema()::text AS current_schema,
    current_setting('search_path')::text AS search_path,
    EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='amaris_staging') AS staging_schema_exists,
    has_schema_privilege(current_user, 'amaris_staging', 'CREATE') AS staging_schema_creatable,
    has_schema_privilege(current_user, 'public', 'CREATE') AS public_schema_creatable,
    (SELECT count(*)
     FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid
     WHERE n.nspname='public' AND c.relkind IN ('r','p')
       AND has_table_privilege(current_user, c.oid, 'SELECT')
    ) AS public_readable_tables,
    (SELECT count(*)
     FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid
     WHERE n.nspname='public' AND c.relkind IN ('r','p')
       AND (has_table_privilege(current_user, c.oid, 'INSERT')
         OR has_table_privilege(current_user, c.oid, 'UPDATE')
         OR has_table_privilege(current_user, c.oid, 'DELETE')
         OR has_table_privilege(current_user, c.oid, 'TRUNCATE'))
    ) AS public_writable_tables
"""


def main() -> int:
    dsn = os.environ.get("STAGING_DATABASE_URL", "")
    if not dsn:
        print(
            "Staging release blocked: staging-only database secret is not configured.",
            file=sys.stderr,
        )
        return 1

    try:
        if is_dedicated_supabase_staging_dsn(dsn):
            with psycopg.connect(
                dsn, connect_timeout=12, sslmode="require", row_factory=dict_row
            ) as conn:
                conn.execute("SET TRANSACTION READ ONLY")
                facts = conn.execute(
                    "SELECT current_database() AS database_name, current_user AS database_role, "
                    "current_schema() AS schema_name"
                ).fetchone()
            if not validate_dedicated_supabase_facts(facts):
                print(
                    "Staging release blocked: dedicated Supabase database identity mismatch.",
                    file=sys.stderr,
                )
                return 1
            print(
                "PASS: actual connection uses the dedicated staging Supabase project and public schema."
            )
            return 0
        # READ ONLY: this check does not run migrations, export records, or create objects.
        with psycopg.connect(dsn, connect_timeout=12, row_factory=dict_row) as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            if is_isolated_render_staging_dsn(dsn):
                facts = conn.execute(
                    "SELECT current_database() AS database_name, current_user AS database_role, "
                    "current_schema() AS schema_name"
                ).fetchone()
                if not validate_render_facts(facts):
                    print(
                        "Staging release blocked: isolated Render database identity mismatch.",
                        file=sys.stderr,
                    )
                    return 1
                print(
                    "PASS: actual Render connection uses the isolated staging database and role."
                )
                return 0
            facts = conn.execute(QUERY).fetchone()
        if facts is None:
            raise RuntimeError("Database returned no verification result.")
        verified, message = validate_facts(facts)
        print(message if verified else "Staging release blocked: " + message)
        return 0 if verified else 1
    except (psycopg.Error, RuntimeError, ValueError, KeyError, TypeError):
        # Never print psycopg exceptions: driver messages can contain connection details.
        print(
            "Staging release blocked: database isolation query failed.", file=sys.stderr
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
