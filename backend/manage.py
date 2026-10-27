#!/usr/bin/env python
import os
import sys


def main() -> None:
    # Render staging runs "python manage.py migrate" on every startup. Refuse to
    # touch the database until the *service's own* connection proves isolation.
    if (
        len(sys.argv) > 1
        and sys.argv[1] == "migrate"
        and os.environ.get("RENDER_SERVICE_ID") == "srv-dam2iivcgkoc7383tq50"
    ):
        from pathlib import Path

        if os.getenv("RENDER_GIT_BRANCH") not in ("staging", "ops/staging-known-good-af8709c-20261019"):
            raise SystemExit("Staging migration blocked: Render is not on the staging branch.")
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "release"))
        from verify_staging_database_isolation import is_isolated_render_staging_dsn
        from verify_staging_database_isolation import is_dedicated_supabase_staging_dsn
        from verify_staging_database_isolation import main as verify_staging_connection

        # The verifier deliberately expects its own variable; bind it to the
        # actual DATABASE_URL that Django will use in THIS Render container.
        configured_url = os.environ.get("DATABASE_URL", "")
        if not configured_url:
            raise SystemExit("Staging migration blocked: DATABASE_URL is not set.")
        isolated_render = is_isolated_render_staging_dsn(configured_url)
        isolated_supabase_staging = is_dedicated_supabase_staging_dsn(configured_url)
        expected_schema = "public" if (isolated_render or isolated_supabase_staging) else "amaris_staging"
        configured_schema = os.environ.get("DATABASE_SCHEMA", "").strip()
        if configured_schema and configured_schema != expected_schema:
            raise SystemExit("Staging migration blocked: invalid Django database schema.")
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
