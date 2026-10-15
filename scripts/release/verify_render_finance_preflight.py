"""Read-only deployment prerequisite checks; never print service secret values.

Use the protected production deployment credential only within this job. Do not
export env vars, credentials, records or bank data to artifacts or job outputs.
The Render startup guard remains authoritative about the final effective DSN.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from cryptography.fernet import Fernet
from verify_staging_database_isolation import is_isolated_render_staging_dsn
from verify_staging_database_isolation import main as verify_staging

STAGING = "srv-dam2iivcgkoc7383tq50"
PRODUCTION = "srv-dapn6b3tqb8s73d3r7n0"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args):
        raise RuntimeError("API redirect rejected")


def api_get(path):
    key = os.environ.get("RENDER_API_KEY")
    if not key:
        raise RuntimeError("Protected Render deployment credential is missing")
    request = urllib.request.Request(
        "https://api.render.com/v1/" + path,
        headers={"Authorization": "Bearer " + key, "Accept": "application/json"},
    )
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=25) as result:
        return json.load(result)


def service_env(service):
    values = {}
    cursor = ""
    for _ in range(10):
        suffix = "?limit=100" + (
            "&cursor=" + urllib.parse.quote(cursor) if cursor else ""
        )
        rows = api_get(f"services/{service}/env-vars" + suffix)
        for row in rows:
            item = row.get("envVar", row)
            values[item["key"]] = item.get("value", "")
        if len(rows) < 100:
            return values
        cursor = rows[-1].get("cursor", "")
        if not cursor:
            raise RuntimeError("Incomplete service environment page")
    raise RuntimeError("Service environment pagination limit")


def main():
    try:
        stage = service_env(STAGING)
        prod = service_env(PRODUCTION)
        for label, values in (("Staging", stage), ("Production", prod)):
            mode = values.get("PAYFAST_MODE", "").strip().lower()
            alias = values.get("PAYFAST_ENV", "").strip().lower()
            valid = {"", "sandbox", "live"}
            if mode not in valid or alias not in valid or (mode and alias and mode != alias):
                raise RuntimeError("Conflicting or invalid direct PayFast environment configuration")
            print(label, "direct PayFast mode:", mode or alias or "not directly configured")
            print(label, "direct PayFast credentials complete:", all(
                bool(values.get(key, "").strip())
                for key in ("PAYFAST_MERCHANT_ID", "PAYFAST_MERCHANT_KEY", "PAYFAST_PASSPHRASE")
            ))
        # Presence only. These are service variables; linked groups are not
        # returned by this API. Missing direct configuration fails closed.
        print(
            "Staging DATABASE_URL directly configured:", bool(stage.get("DATABASE_URL"))
        )
        print(
            "Production bank vault key directly configured:",
            bool(prod.get("TUTOR_BANK_FERNET_KEY")),
        )
        print("Production SMTP host directly configured:", bool(prod.get("EMAIL_HOST")))
        print(
            "Production SMTP credential directly configured:",
            bool(prod.get("EMAIL_HOST_PASSWORD") or prod.get("GMAIL_APP_PASSWORD")),
        )
        bank = prod.get("TUTOR_BANK_FERNET_KEY")
        if bank:
            Fernet(bank.encode())
            print("Production bank vault key format: valid")
        dsn = stage.get("DATABASE_URL", "")
        if not dsn:
            raise RuntimeError(
                "Staging service lacks a directly configured database connection"
            )
        stage_url = urllib.parse.urlsplit(dsn)
        prod_url = urllib.parse.urlsplit(prod.get("DATABASE_URL", ""))
        project = "epkcuseloinygkakxxdu"
        print(
            "Staging references production Supabase project:",
            project in ((stage_url.hostname or "") + (stage_url.username or "")),
        )
        print(
            "Staging and production database hosts match:",
            bool(stage_url.hostname and stage_url.hostname == prod_url.hostname),
        )
        print(
            "Staging host appears to be Render PostgreSQL:",
            (stage_url.hostname or "").startswith("dpg-"),
        )
        if is_isolated_render_staging_dsn(dsn):
            if stage.get("DATABASE_SCHEMA", "") not in ("", "public"):
                raise RuntimeError(
                    "Isolated Render staging database has an unexpected schema override"
                )
            print(
                "PASS: configured DSN matches the exact, separate Render staging database resource."
            )
            print(
                "Internal Render connection proof is mandatory in manage.py before any migration; external access stays blocked."
            )
            return 0
        if "amaris_staging_app" not in (stage_url.username or ""):
            raise RuntimeError(
                "Staging service is not configured with its restricted database role"
            )
        schema = stage.get("DATABASE_SCHEMA", "")
        if schema and schema != "amaris_staging":
            raise RuntimeError("Staging DATABASE_SCHEMA is not isolated")
        os.environ["STAGING_DATABASE_URL"] = dsn
        if verify_staging() != 0:
            return 1
        print(
            "PASS: actual directly configured Render staging database passed read-only isolation checks"
        )
        return 0
    except (urllib.error.HTTPError, urllib.error.URLError):
        print(
            "Release blocked: Render API read-only preflight failed; no configuration changed",
            file=sys.stderr,
        )
        return 1
    except (ValueError, TypeError, KeyError):
        print(
            "Release blocked: invalid or incomplete service configuration; no configuration changed",
            file=sys.stderr,
        )
        return 1
    except RuntimeError as error:
        # RuntimeError messages here are fixed source strings, never driver errors.
        print("Release blocked:", str(error), file=sys.stderr)
        return 1
    finally:
        os.environ.pop("STAGING_DATABASE_URL", None)


if __name__ == "__main__":
    raise SystemExit(main())
