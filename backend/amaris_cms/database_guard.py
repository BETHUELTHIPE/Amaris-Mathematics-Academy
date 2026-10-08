"""Fail-closed routing for a single Supabase PostgreSQL application database.

Never include a DATABASE_URL or password in diagnostic errors.
"""
from urllib.parse import urlsplit


def validate_supabase_database_url(url: str, *, ssl_required: bool, project_ref: str) -> None:
    """Reject SQLite, Render Postgres, unrelated Supabase projects and transaction pooling."""
    if not ssl_required:
        raise RuntimeError("Supabase-only mode requires DATABASE_SSL_REQUIRED=true.")
    if not url:
        raise RuntimeError("Supabase-only mode requires DATABASE_URL.")
    if not project_ref or not project_ref.isalnum():
        raise RuntimeError("Invalid Supabase project reference.")

    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        port = parsed.port
        username = parsed.username or ""
        has_password = bool(parsed.password)
    except ValueError as exc:
        raise RuntimeError("Invalid Supabase DATABASE_URL.") from None

    if parsed.scheme not in {"postgresql", "postgres"} or not username or not has_password:
        raise RuntimeError("Supabase-only mode requires a PostgreSQL connection with credentials.")
    if port != 5432:
        raise RuntimeError("Use Supabase PostgreSQL direct/session mode on port 5432.")

    direct = host == f"db.{project_ref}.supabase.co"
    session_pooler = host.endswith(".pooler.supabase.com") and username.endswith(f".{project_ref}")
    if not (direct or session_pooler):
        raise RuntimeError("DATABASE_URL must reference the configured Supabase PostgreSQL project.")
