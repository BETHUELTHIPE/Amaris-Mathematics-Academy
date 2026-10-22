#!/usr/bin/env python
import os
import sys


def is_approved_staging_migration_branch(branch: str) -> bool:
    """Only the original staging branch and the pinned recovered staging branch may migrate."""
    return branch in {"staging", "ops/staging-known-good-af8709c-20261019"}


def main() -> None:
    # Render staging runs "python manage.py migrate" on every startup. Refuse to
    # touch the database until the *service's own* connection proves isolation.
    if (
        len(sys.argv) > 1
        and sys.argv[1] == "migrate"
        and os.environ.get("RENDER_SERVICE_ID") == "srv-dam2iivcgkoc7383tq50"
    ):
        from pathlib import Path

        if not is_approved_staging_migration_branch(os.getenv("RENDER_GIT_BRANCH", "")):
            raise SystemExit("Staging migration blocked: Render is not on an approved staging branch.")
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "release"))
        from verify_staging_database_isolation import (
            SUPABASE_STAGE_REF,
            is_dedicated_supabase_staging_dsn,
            is_isolated_render_staging_dsn,
            validate_dedicated_staging_bindings,
        )
        from verify_staging_database_isolation import main as verify_staging_connection

        # The verifier deliberately expects its own variable; bind it to the
        # actual DATABASE_URL that Django will use in THIS Render container.
        configured_url = os.environ.get("DATABASE_URL", "")
        if not configured_url:
            raise SystemExit("Staging migration blocked: DATABASE_URL is not set.")
        isolated_render = is_isolated_render_staging_dsn(configured_url)
        dedicated_supabase = is_dedicated_supabase_staging_dsn(configured_url)
        expected_schema = "public" if isolated_render or dedicated_supabase else "amaris_staging"
        configured_schema = os.environ.get("DATABASE_SCHEMA", "").strip()
        if configured_schema and configured_schema != expected_schema:
            raise SystemExit("Staging migration blocked: invalid Django database schema.")
        if dedicated_supabase and os.getenv("SUPABASE_PROJECT_REF") != SUPABASE_STAGE_REF:
            raise SystemExit("Staging migration blocked: Supabase project configuration mismatch.")
        if dedicated_supabase and not validate_dedicated_staging_bindings(os.environ):
            raise SystemExit("Staging migration blocked: Auth and Storage must use the dedicated staging project.")
        os.environ["STAGING_DATABASE_URL"] = configured_url
        if verify_staging_connection() != 0:
            raise SystemExit("Staging migration blocked: unsafe database connection.")
        os.environ.pop("STAGING_DATABASE_URL", None)
        if isolated_render:
            # Only this explicitly identified staging service/database may use
            # Render Postgres. Production Supabase enforcement is unchanged.
            os.environ["SUPABASE_DATABASE_REQUIRED"] = "false"
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
