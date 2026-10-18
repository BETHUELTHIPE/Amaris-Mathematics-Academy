"""Fail closed before Django schema migrations on hosted Amaris services.

The Render service must migrate only its intended Supabase PostgreSQL project.
No credentials, database URL, or username are ever included in an error.
"""

from collections.abc import Mapping
from typing import Any

STAGING_PROJECT = "atyhhjwwxgzeurnwayay"
PRODUCTION_PROJECT = "epkcuseloinygkakxxdu"


def validate_migration_database(
    database: Mapping[str, Any],
    *,
    service_name: str = "",
    deployment_environment: str = "",
    on_render: bool = False,
) -> None:
    """Validate the target database without opening a connection or changing schema."""
    service = service_name.strip().lower()
    environment = deployment_environment.strip().lower()

    if environment not in {"", "staging", "production"}:
        raise RuntimeError("Migration blocked: invalid AMARIS_DEPLOY_ENV.")

    if not environment:
        if "staging" in service:
            environment = "staging"
        elif service == "amaris-production-web":
            environment = "production"
        elif on_render:
            raise RuntimeError("Migration blocked: unknown Render service environment.")
        else:
            return  # Local tests and developer databases have their own safeguards.

    if ("staging" in service and environment != "staging") or (
        service == "amaris-production-web" and environment != "production"
    ):
        raise RuntimeError("Migration blocked: deployment environment conflicts with Render service.")

    if database.get("ENGINE") != "django.db.backends.postgresql":
        raise RuntimeError("Migration blocked: hosted deployment requires PostgreSQL.")

    expected = STAGING_PROJECT if environment == "staging" else PRODUCTION_PROJECT
    host = str(database.get("HOST") or "").strip().lower().rstrip(".")
    user = str(database.get("USER") or "").strip().lower()

    direct = host == f"db.{expected}.supabase.co" and user in {"postgres", f"postgres.{expected}"}
    pooled = host.endswith(".pooler.supabase.com") and user == f"postgres.{expected}"
    if not (direct or pooled):
        raise RuntimeError(f"Migration blocked: database is not the approved {environment} Supabase project.")
