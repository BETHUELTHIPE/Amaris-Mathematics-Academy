from collections.abc import Mapping
from typing import Any


def assert_supabase_database(database: Mapping[str, Any], project_ref: str) -> None:
    """Fail closed when a protected environment is not using the configured Supabase Postgres project."""
    ref = project_ref.strip().lower()
    if not ref:
        raise RuntimeError("SUPABASE_PROJECT_REF must be configured when Supabase database enforcement is enabled.")

    engine = str(database.get("ENGINE", "")).strip()
    host = str(database.get("HOST", "")).strip().lower().rstrip(".")
    user = str(database.get("USER", "")).strip().lower()

    if engine != "django.db.backends.postgresql":
        raise RuntimeError("Protected staging/production environments must use Supabase PostgreSQL.")

    direct_host = f"db.{ref}.supabase.co"
    expected_pooler_user = f"postgres.{ref}"

    direct_connection = host == direct_host and user == "postgres"
    pooled_connection = host.endswith(".pooler.supabase.com") and user == expected_pooler_user

    if not (direct_connection or pooled_connection):
        raise RuntimeError(
            "Protected staging/production DATABASE_URL must point to the configured Supabase project."
        )
