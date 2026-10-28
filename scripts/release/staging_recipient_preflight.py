"""Read-only deployment guard for the existing Amaris staging notification runtime."""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen

import psycopg
from psycopg.rows import dict_row

STAGE_SERVICE = "srv-dam2iivcgkoc7383tq50"
PRODUCTION_SERVICE = "srv-dapn6b3tqb8s73d3r7n0"
WORKSPACE = "tea-csppi8l6l47c73dk9c90"
EXPECTED_LIVE_SHA = "7b6296905e7dc5765a58175d18e24163f3bb5a2e"
STAGE_PROJECT = "atyhhjwwxgzeurnwayay"
PRODUCTION_PROJECT = "epkcuseloinygkakxxdu"
APPROVED_MAILBOXES = {"bethuelmoukangwe30@gmail.com", "bethuelmoukangwe8@gmail.com"}
APPROVED_OPERATIONS_MAILBOX = "bethuelmoukangwe8@gmail.com"


def render_get(path: str):
    request = Request(
        "https://api.render.com/v1/" + path,
        headers={"Authorization": "Bearer " + os.environ["RENDER_TOKEN"], "Accept": "application/json"},
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def service_env(service: str) -> dict[str, str]:
    values = {}
    cursor = ""
    for _ in range(10):
        suffix = "&cursor=" + cursor if cursor else ""
        page = render_get(f"services/{service}/env-vars?limit=100{suffix}")
        if not isinstance(page, list):
            raise RuntimeError("Environment metadata was not a list")
        for entry in page:
            variable = entry.get("envVar", entry)
            if isinstance(variable.get("key"), str) and isinstance(variable.get("value"), str):
                values[variable["key"]] = variable["value"]
        if len(page) < 100 or not page[-1].get("cursor"):
            return values
        cursor = page[-1]["cursor"]
    raise RuntimeError("Environment pagination did not complete")


def matches_project(dsn: str, project: str) -> bool:
    parsed = urlsplit(dsn)
    host = (parsed.hostname or "").lower()
    user = unquote(parsed.username or "")
    return bool(
        parsed.scheme in {"postgres", "postgresql"}
        and parsed.password
        and unquote(parsed.path).lstrip("/") == "postgres"
        and (
            (host == f"db.{project}.supabase.co" and bool(user))
            or (host.endswith(".pooler.supabase.com") and user.endswith("." + project))
        )
    )


def broker_identity(value: str) -> tuple[str | None, int | None, str]:
    parsed = urlsplit(value)
    if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
        raise RuntimeError("Broker identity unavailable")
    return parsed.hostname, parsed.port or 6379, parsed.path or "/0"


def main() -> None:
    if not os.environ.get("RENDER_TOKEN"):
        raise SystemExit("BLOCK: protected staging Render credential is unavailable")
    for service in (STAGE_SERVICE, PRODUCTION_SERVICE):
        details = render_get(f"services/{service}")
        if details.get("ownerId") != WORKSPACE or details.get("id") != service:
            raise SystemExit("BLOCK: service identity or workspace mismatch")
    records = render_get(f"services/{STAGE_SERVICE}/deploys?limit=10")
    deployments = [item.get("deploy", item) for item in records]
    live = next((item for item in deployments if item.get("status") == "live"), None)
    if not live or live.get("commit", {}).get("id") != EXPECTED_LIVE_SHA:
        raise SystemExit("BLOCK: staging baseline changed; reconcile before deploying")
    active = {"created", "build_in_progress", "pre_deploy_in_progress", "update_in_progress"}
    if any(item.get("status") in active for item in deployments):
        raise SystemExit("BLOCK: another staging deployment is active")

    stage = service_env(STAGE_SERVICE)
    production = service_env(PRODUCTION_SERVICE)
    if not matches_project(stage.get("DATABASE_URL", ""), STAGE_PROJECT):
        raise SystemExit("BLOCK: actual staging database is not the dedicated staging project")
    if not matches_project(production.get("DATABASE_URL", ""), PRODUCTION_PROJECT):
        raise SystemExit("BLOCK: production database binding changed; reconcile environment identity")
    if broker_identity(stage.get("CELERY_BROKER_URL", "")) == broker_identity(production.get("CELERY_BROKER_URL", "")):
        raise SystemExit("BLOCK: staging and production notification brokers are not isolated")
    if stage.get("AMARIS_COLOCATE_NOTIFICATIONS", "").lower() not in {"1", "true", "yes"}:
        raise SystemExit("BLOCK: staging notification worker supervision is disabled")
    if not all(stage.get(key) for key in ("EMAIL_HOST", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD")):
        raise SystemExit("BLOCK: staging SMTP configuration is incomplete")

    connection_parameters = psycopg.conninfo.conninfo_to_dict(stage["DATABASE_URL"])
    connection_parameters.setdefault("sslmode", "require")
    connection_parameters["connect_timeout"] = 12
    connection_parameters["options"] = "-c search_path=public -c default_transaction_read_only=on"
    with psycopg.connect(**connection_parameters, row_factory=dict_row) as connection:
        fields = connection.execute(
            "select column_name from information_schema.columns "
            "where table_schema='public' and table_name='content_liveclassbooking'"
        ).fetchall()
        present = {item["column_name"] for item in fields}
        if not {"confirmation_sent_at", "tutor_confirmation_sent_at", "admin_confirmation_sent_at"} <= present:
            raise SystemExit("BLOCK: staging recipient receipt columns are missing")
        site = connection.execute("select email from public.content_sitesettings order by id limit 1").fetchone()
        administrator = (stage.get("BOOKING_ADMIN_EMAIL") or (site["email"] if site else APPROVED_OPERATIONS_MAILBOX)).strip().lower()
        if administrator != APPROVED_OPERATIONS_MAILBOX:
            raise SystemExit("BLOCK: configured administrator recipient differs from approved test mailbox")
        pending = connection.execute(
            "select s.email as student_email,u.email as tutor_email,b.confirmation_sent_at,"
            "b.tutor_confirmation_sent_at,b.admin_confirmation_sent_at "
            "from public.content_liveclassbooking b "
            "join public.content_studentrecord s on s.id=b.student_id "
            "join public.content_tutoravailabilityslot t on t.id=b.slot_id "
            "join public.auth_user u on u.id=t.tutor_id "
            "where b.status='confirmed' and b.gateway_verified_at is not null and b.paid_at is not null "
            "and (b.confirmation_sent_at is null or b.tutor_confirmation_sent_at is null "
            "or b.admin_confirmation_sent_at is null)"
        ).fetchall()
        for booking in pending:
            if (
                booking["student_email"].lower() not in APPROVED_MAILBOXES
                or booking["tutor_email"].lower() != APPROVED_OPERATIONS_MAILBOX
                or booking["confirmation_sent_at"] is None
            ):
                raise SystemExit("BLOCK: pending staging notification would contact an unapproved recipient")
        pending_roles = sum(
            int(item["tutor_confirmation_sent_at"] is None) + int(item["admin_confirmation_sent_at"] is None)
            for item in pending
        )

    print("PASS: actual Render staging database and broker are isolated from production")
    print("PASS: existing staging worker supervision and SMTP configuration are present")
    print("PASS: recipient columns and approved tutor/administrator destinations verified")
    print(f"Pending approved already-paid bookings: {len(pending)}; missing tutor/admin messages: {pending_roles}")
    print("READ ONLY: no payment, booking, receipt, secret or service configuration was changed")


if __name__ == "__main__":
    try:
        main()
    except (HTTPError, URLError, OSError, RuntimeError, ValueError, KeyError, TypeError, psycopg.Error):
        raise SystemExit("BLOCK: staging runtime preflight could not complete; sensitive provider details suppressed") from None
