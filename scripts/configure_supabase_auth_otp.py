#!/usr/bin/env python3
"""Check or install Amaris six-digit Supabase Auth email templates.

Uses Supabase Management API, not Postgres SQL and not a service-role key.
Requires a scoped SUPABASE_ACCESS_TOKEN. Never prints or logs the token,
SMTP passwords, or the fetched Auth configuration.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / "frontend" / "email-templates"
FIELDS = {
    "mailer_templates_confirmation_content": "confirm-signup.html",
    "mailer_templates_magic_link_content": "magic-link-login.html",
    "mailer_templates_recovery_content": "recovery.html",
}
SUBJECTS = {
    "mailer_subjects_confirmation": "Amaris | Verify your student email",
    "mailer_subjects_magic_link": "Amaris | Your six-digit sign-in code",
    "mailer_subjects_recovery": "Amaris | Reset your password",
}
PROJECT_REF = re.compile(r"^[a-z0-9]{20}$")
API_ORIGIN = "https://api.supabase.com"


def desired_config() -> dict[str, object]:
    config: dict[str, object] = {
        "mailer_autoconfirm": False,
        "mailer_otp_length": 6,
        "mailer_otp_exp": 600,
        **SUBJECTS,
    }
    for setting, filename in FIELDS.items():
        value = (TEMPLATE_DIR / filename).read_text(encoding="utf-8")
        if "{{ .Token }}" not in value:
            raise ValueError(f"{filename} is missing Supabase's .Token placeholder")
        if filename == "recovery.html" and (
            "{{ .TokenHash }}" not in value or "{{ .RedirectTo }}" not in value
        ):
            raise ValueError("Recovery email is missing preview-safe recovery link placeholders")
        config[setting] = value
    return config


def request_config(method: str, ref: str, access_token: str, payload: dict | None = None) -> dict:
    url = f"{API_ORIGIN}/v1/projects/{ref}/config/auth"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    request = Request(url, method=method, headers=headers, data=body)
    try:
        with urlopen(request, timeout=20) as response:
            result = json.load(response)
    except HTTPError as exc:
        # Never print provider response bodies (can contain credentials).
        raise RuntimeError(f"Supabase Auth Management API {method} failed (HTTP {exc.code})") from None
    except (URLError, TimeoutError):
        raise RuntimeError("Supabase Auth Management API is unreachable") from None
    if not isinstance(result, dict):
        raise RuntimeError("Supabase Auth Management API returned an unexpected format")
    return result


def status_of(config: dict) -> dict[str, bool]:
    expected = desired_config()
    result = {field: config.get(field) == value for field, value in expected.items()}
    # Custom SMTP is configured outside this script; presence does NOT prove inbox receipt.
    result["auth_email_enabled"] = config.get("external_email_enabled") is True
    result["smtp_host_configured"] = bool(config.get("smtp_host"))
    result["smtp_sender_configured"] = bool(config.get("smtp_admin_email"))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-ref", required=True)
    parser.add_argument("--mode", choices=["check", "apply"], default="check")
    args = parser.parse_args(argv)
    if not PROJECT_REF.fullmatch(args.project_ref):
        parser.error("Invalid Supabase project reference")
    token = os.environ.get("SUPABASE_ACCESS_TOKEN", "")
    if not token:
        print("Missing SUPABASE_ACCESS_TOKEN (scoped Management API credential).", file=sys.stderr)
        return 2

    try:
        existing = request_config("GET", args.project_ref, token)
        if args.mode == "apply":
            if not existing.get("smtp_host") or not existing.get("smtp_admin_email"):
                print("No custom Auth SMTP host/sender is configured; fix SMTP in Supabase first.", file=sys.stderr)
                return 3
            if existing.get("external_email_enabled") is False:
                print("Supabase Auth Email provider is disabled; enable it first.", file=sys.stderr)
                return 3
            request_config("PATCH", args.project_ref, token, desired_config())
            existing = request_config("GET", args.project_ref, token)
        status = status_of(existing)
        # Safe to log flags; never print SMTP passwords or HTML email content.
        for key in sorted(status):
            print(f"{key}: {'OK' if status[key] else 'NOT_CONFIGURED'}")
        if all(status.values()):
            print("Auth configuration matches desired six-digit templates and SMTP presence checks.")
            print("Live email inbox delivery, rate-limit behavior, and code redemption STILL require E2E validation.")
            return 0
        return 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Unable to verify Supabase Auth config: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
