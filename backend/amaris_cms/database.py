from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit


def requires_supabase_database(environ: Mapping[str, str]) -> bool:
    """Keep Render production on Supabase; permit explicitly isolated staging Postgres.

    Opting out is allowed only when the deployment explicitly identifies itself
    as staging AND SUPABASE_DATABASE_REQUIRED is explicitly false. Every other
    Render deployment continues to require Supabase, including production.
    """
    render = bool(environ.get("RENDER"))
    override = environ.get("SUPABASE_DATABASE_REQUIRED", "")
    enabled = override.strip().lower() in {"1", "true", "yes", "on"}
    staging = (
        environ.get("AMARIS_DEPLOYMENT_ENVIRONMENT", "").strip().lower() == "staging"
    )

    opted_out = staging and override.strip().lower() in {"0", "false", "no", "off"}
    if render and not opted_out:
        return True
    if render:
        return False
    return enabled


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
