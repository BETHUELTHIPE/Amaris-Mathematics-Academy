"""Read-only gate: do not deploy Render staging unless its *actual* DB credentials are isolated.

This is deliberately an independent connection using a staging-only protected GitHub
environment secret. Never fall back to the production DATABASE_URL.
"""

from __future__ import annotations

import os
import sys


EXPECTED_ROLE = "amaris_staging_app"
EXPECTED_SCHEMA = "amaris_staging"


def validate_facts(facts: dict[str, object]) -> tuple[bool, str]:
    """Fail closed if this DB connection could touch production public tables."""
    if facts["current_user"] != EXPECTED_ROLE:
        return False, "Database connection does not use the restricted staging role."
    if facts["current_schema"] != EXPECTED_SCHEMA:
        return False, "Database connection would create Django tables outside the staging schema."
    first_path = str(facts["search_path"]).split(",")[0].strip().strip('"')
    if first_path != EXPECTED_SCHEMA:
        return False, "The effective search path does not start with the staging schema."
    if not facts["staging_schema_exists"] or not facts["staging_schema_creatable"]:
        return False, "The staging schema is missing or not writable by the staging role."
    if facts["public_schema_creatable"]:
        return False, "Staging role could create database objects in production public schema."
    if facts["public_readable_tables"] or facts["public_writable_tables"]:
        return False, "Staging database role can access production public tables."
    return True, "Restricted staging connection verified. No production table privileges."


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
        print("Staging release blocked: staging-only database secret is not configured.", file=sys.stderr)
        return 1

    try:
        import psycopg
        from psycopg.rows import dict_row

        # READ ONLY: this check does not run migrations, export records, or create objects.
        with psycopg.connect(dsn, connect_timeout=12, row_factory=dict_row) as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            facts = conn.execute(QUERY).fetchone()
        if facts is None:
            raise RuntimeError("Database returned no verification result.")
        verified, message = validate_facts(facts)
        print(message if verified else "Staging release blocked: " + message)
        return 0 if verified else 1
    except Exception:
        # Never print psycopg exceptions: driver messages can contain connection details.
        print("Staging release blocked: database isolation query failed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
