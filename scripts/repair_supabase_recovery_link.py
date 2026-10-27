#!/usr/bin/env python3
"""Repair only the recovery-link href in a hosted Supabase template.

Preserves the existing professional Amaris letterhead, text, styles and sender
configuration. It never prints the template, recovery tokens or SMTP settings.
This is an explicit, separately approved apply path; audit mode is read-only.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from urllib.parse import urlsplit

from configure_supabase_auth_otp import request_config

PRODUCTION_REF = "epkcuseloinygkakxxdu"
STAGING_REF = "atyhhjwwxgzeurnwayay"
PRODUCTION_SITE = "https://amaris-mathematics-academy-live-students.onrender.com"
TARGET_HREF = "{{ .SiteURL }}/reset-password/verify?token_hash={{ .TokenHash }}"
HREF_WITH_TOKEN_HASH = re.compile(
    r"href=(?P<quote>[\"'])(?P<value>[^\"']*token_hash=\{\{\s*\.TokenHash\s*\}\}[^\"']*)(?P=quote)",
    re.IGNORECASE,
)


def repair_link_preserving_letterhead(html: str) -> str:
    if "{{ .Token }}" not in html or "{{ .TokenHash }}" not in html:
        raise ValueError("Recovery email must provide both a six-digit code and token-hash link.")
    found = list(HREF_WITH_TOKEN_HASH.finditer(html))
    if len(found) != 1:
        raise ValueError("Expected exactly one recovery link with a Supabase TokenHash.")
    candidate = found[0]
    url = candidate.group("value")
    if TARGET_HREF == url:
        return html
    if "{{ .RedirectTo }}" not in url and "localhost" not in url.lower() and "{{ .SiteURL }}" not in url:
        raise ValueError("Recovery URL differs from known formats; do not modify unrelated links.")
    return html[:candidate.start("value")] + TARGET_HREF + html[candidate.end("value"):]


def safe_site(url: object, ref: str) -> bool:
    if not isinstance(url, str):
        return False
    split = urlsplit(url)
    if split.scheme != "https" or not split.hostname or split.username or split.password:
        return False
    if split.hostname in ("localhost", "127.0.0.1", "::1") or split.path not in ("", "/"):
        return False
    if ref == PRODUCTION_REF:
        return url.rstrip("/") == PRODUCTION_SITE
    return url.rstrip("/").startswith("https://amaris-mathematics-academy-staging")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", choices=("staging", "production"), required=True)
    parser.add_argument("--mode", choices=("check", "apply"), default="check")
    parser.add_argument("--confirmation", default="")
    args = parser.parse_args(argv)
    ref = PRODUCTION_REF if args.project == "production" else STAGING_REF
    if args.mode == "apply" and args.confirmation != f"APPLY_RECOVERY_LINK_{args.project.upper()}":
        print("An explicit exact project-specific apply confirmation is required.", file=sys.stderr)
        return 3
    access_token = os.environ.get("SUPABASE_ACCESS_TOKEN")
    if not access_token:
        print("Missing protected Supabase Management API token.", file=sys.stderr)
        return 2
    try:
        existing = request_config("GET", ref, access_token)
        if not safe_site(existing.get("site_url"), ref):
            print("Auth Site URL is not an approved HTTPS Amaris site; no changes made.", file=sys.stderr)
            return 3
        if not existing.get("smtp_host") or not existing.get("smtp_admin_email"):
            print("Auth SMTP/sender not configured; no changes made.", file=sys.stderr)
            return 3
        original = existing.get("mailer_templates_recovery_content")
        if not isinstance(original, str):
            raise ValueError("Missing hosted password recovery template.")
        updated = repair_link_preserving_letterhead(original)
        if updated == original:
            print("PASS: Recovery link is canonical; hosted branding unchanged.")
            return 0
        if args.mode == "check":
            print("BLOCK: Hosted recovery link needs repair; no changes made.")
            return 1
        request_config("PATCH", ref, access_token, {"mailer_templates_recovery_content": updated})
        verified = request_config("GET", ref, access_token)
        if verified.get("mailer_templates_recovery_content") != updated:
            raise ValueError("Updated recovery link failed read-back verification.")
        print("PASS: Recovery link repaired and independently read back; all other email template content preserved.")
        return 0
    except (ValueError, OSError, RuntimeError) as error:
        print(f"Recovery link repair failed safely: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
