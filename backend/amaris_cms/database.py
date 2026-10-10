from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit


def validate_supabase_database(database: Mapping[str, Any], project_url: str, project_ref: str = "") -> None:
    """Reject local databases and connections to a different hosted project."""
    if database.get("ENGINE") != "django.db.backends.postgresql":
        raise RuntimeError("The deployed database must use Supabase PostgreSQL.")

    api_host = urlsplit(project_url).hostname or ""
    if not project_ref and api_host.endswith(".supabase.co"):
        project_ref = api_host.removesuffix(".supabase.co")
    if not project_ref or not project_ref.isalnum():
        raise RuntimeError("Set SUPABASE_URL or SUPABASE_DATABASE_PROJECT_REF to identify the database project.")
    if api_host and api_host != f"{project_ref}.supabase.co":
        raise RuntimeError("Supabase Auth and the database must use the same project.")

    host = str(database.get("HOST", "")).lower()
    user = str(database.get("USER", ""))
    direct = host == f"db.{project_ref}.supabase.co"
    pooled = host.endswith(".pooler.supabase.com") and user.endswith(f".{project_ref}")
    if not (direct or pooled):
        raise RuntimeError("DATABASE_URL must connect to the configured Supabase project.")
    if str(database.get("PORT") or "5432") != "5432":
        raise RuntimeError("Use the Supabase session pooler on port 5432 for Django.")
    if database.get("OPTIONS", {}).get("sslmode") not in {"require", "verify-ca", "verify-full"}:
        raise RuntimeError("Supabase PostgreSQL requires TLS; set DATABASE_SSL_REQUIRED=true.")

# Only this specific Render staging service may connect to the dedicated Render DB.
_RENDER_STAGING_SERVICE_ID = "srv-dam2iivcgkoc7383tq50"
_RENDER_STAGING_DATABASE_HOST = "dpg-dam2gj6k1f9s73e81tmg-a"


def is_render_staging_service(service_id: str, branch: str) -> bool:
    """Keep the Render database exception exclusive to the staging service."""
    return service_id == _RENDER_STAGING_SERVICE_ID and branch == "staging"


def validate_render_staging_database(database: Mapping[str, Any]) -> None:
    """Fail closed unless staging targets its own Render Postgres instance."""
    if database.get("ENGINE") != "django.db.backends.postgresql":
        raise RuntimeError("Staging must use Render PostgreSQL.")

    host = str(database.get("HOST") or "").strip().lower().rstrip(".")
    if host != _RENDER_STAGING_DATABASE_HOST and not host.startswith(
        _RENDER_STAGING_DATABASE_HOST + "."
    ):
        raise RuntimeError("Staging DATABASE_URL must use amaris-staging-postgres on Render.")
    if database.get("NAME") != "amaris_staging_postgres":
        raise RuntimeError("Staging DATABASE_URL must use the staging database name.")
    if database.get("USER") != "amaris_staging_postgres_user":
        raise RuntimeError("Staging DATABASE_URL must use the staging database user.")
    if str(database.get("PORT") or "5432") != "5432":
        raise RuntimeError("Staging PostgreSQL must use port 5432.")
