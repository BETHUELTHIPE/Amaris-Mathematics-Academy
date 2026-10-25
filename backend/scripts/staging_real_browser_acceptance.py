"""Real Chromium staging authentication smoke with strictly nonproduction endpoints.

Default: anonymous browser checks. Authenticated checks require explicit
protected staging fixture credentials and a workflow dispatch confirmation.
This deliberately does not create users, bookings, send emails or pay anyone.
"""
from __future__ import annotations

import argparse
import json
import os
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

BACKEND = "https://amaris-mathematics-academy-staging.onrender.com"
FRONTEND = "https://amaris-mathematics-academy-staging-x4ax.onrender.com"
AUTH = "https://atyhhjwwxgzeurnwayay.supabase.co"


def assert_staging_only() -> None:
    for base, host in ((BACKEND, "amaris-mathematics-academy-staging.onrender.com"),
                       (FRONTEND, "amaris-mathematics-academy-staging-x4ax.onrender.com"),
                       (AUTH, "atyhhjwwxgzeurnwayay.supabase.co")):
        parsed = urlparse(base)
        if parsed.scheme != "https" or parsed.hostname != host:
            raise RuntimeError("BLOCK: unexpected staging origin")
    if os.environ.get("PAYFAST_MODE", "sandbox") != "sandbox":
        raise RuntimeError("BLOCK: PayFast must remain sandbox")
    for name in ("DATABASE_URL", "PAYFAST_MERCHANT_KEY", "PAYFAST_PASSPHRASE"):
        if os.environ.get(name):
            raise RuntimeError(f"BLOCK: browser acceptance must not receive {name}")


def require(name: str) -> str:
    value = os.environ.get(name, "")
    if not value or len(value) < 2 or "\n" in value or "\r" in value:
        raise RuntimeError(f"BLOCK: missing protected staging fixture credential {name}")
    return value


def check_status(response, expected: set[int], label: str):
    status = response.status if response else 0
    if status not in expected:
        raise AssertionError(f"{label}: HTTP {status}; expected {sorted(expected)}")
    print(f"PASS {label}: HTTP {status}", flush=True)


def public_browser(browser):
    context = browser.new_context(ignore_https_errors=False)
    page = context.new_page()
    response = page.goto(FRONTEND + "/login", wait_until="domcontentloaded", timeout=60000)
    check_status(response, {200}, "staging student login public page")
    try:
        page.locator('input[name="email"]').wait_for(timeout=25000)
        page.locator('input[name="password"]').wait_for(timeout=25000)
    except Exception as exc:
        # Do not echo arbitrary page content, which might contain PII or tokens.
        print("STAGING_FRONTEND_FORM_PRESENT=NO; final_host=" + str(urlparse(page.url).hostname), flush=True)
        raise AssertionError("Staging student login form not rendered by live frontend") from exc
    print("PASS staging student login form rendered in Chromium", flush=True)

    response = page.goto(BACKEND + "/health/ready/", wait_until="domcontentloaded", timeout=35000)
    check_status(response, {200}, "staging Django and database ready")
    for endpoint in ("/api/v1/tutor/dashboard/", "/api/v1/tutor/earnings/"):
        response = page.goto(BACKEND + endpoint, wait_until="domcontentloaded", timeout=35000)
        check_status(response, {401, 403}, "unauthenticated tutor endpoint denied")
    response = page.goto(BACKEND + "/admin/login/", wait_until="domcontentloaded", timeout=35000)
    check_status(response, {200}, "Django admin login")
    if page.locator('input[name="username"]').count() != 1:
        raise AssertionError("Django admin username field missing")
    context.close()


def authenticated_tutor(browser):
    email = require("STAGING_TEST_TUTOR_EMAIL")
    password = require("STAGING_TEST_TUTOR_PASSWORD")
    key = require("STAGING_SUPABASE_PUBLISHABLE_KEY")
    if "@example" in email or "@" not in email:
        raise RuntimeError("BLOCK: tutor must be a configured real staging-only test user")
    context = browser.new_context(ignore_https_errors=False)
    response = context.request.post(
        AUTH + "/auth/v1/token?grant_type=password",
        headers={"apikey": key, "Content-Type": "application/json"},
        data=json.dumps({"email": email, "password": password}),
        timeout=35000,
    )
    if response.status != 200:
        raise AssertionError(f"Staging Supabase tutor authentication rejected: HTTP {response.status}")
    token_data = response.json()
    token = token_data.get("access_token", "")
    if not token or (token_data.get("user", {}).get("email") or "").lower() != email.lower():
        raise AssertionError("Invalid staged tutor identity")
    print("PASS real staging Supabase tutor password grant (credentials masked)", flush=True)

    page = context.new_page()
    def add_token(route):
        # Only the staging tutor endpoint receives this short-lived bearer.
        route.continue_(headers={**route.request.headers, "Authorization": "Bearer " + token})
    page.route(BACKEND + "/api/v1/tutor/**", add_token)
    for endpoint in ("/api/v1/tutor/dashboard/", "/api/v1/tutor/earnings/"):
        response = page.goto(BACKEND + endpoint, wait_until="domcontentloaded", timeout=35000)
        check_status(response, {200}, "authenticated tutor endpoint")
    # A Supabase tutor token must not grant Django Admin/superuser access.
    response = page.goto(BACKEND + "/admin/content/announcement/", wait_until="domcontentloaded", timeout=35000)
    if response.status == 200 and "/admin/login/" not in page.url:
        raise AssertionError("SECURITY: tutor gained superuser Django Admin access")
    print("PASS tutor not authorized for Django superuser Admin", flush=True)
    context.close()


def authenticated_superuser(browser):
    username = require("STAGING_TEST_SUPERUSER_USERNAME")
    password = require("STAGING_TEST_SUPERUSER_PASSWORD")
    context = browser.new_context(ignore_https_errors=False)
    page = context.new_page()
    response = page.goto(BACKEND + "/admin/login/?next=/admin/", timeout=35000)
    check_status(response, {200}, "real Django admin sign-in page")
    page.locator('input[name="username"]').fill(username)
    page.locator('input[name="password"]').fill(password)
    page.locator('input[type="submit"]').first.click()
    page.wait_for_load_state("domcontentloaded", timeout=20000)
    if not page.url.startswith(BACKEND + "/admin/") or "/admin/login/" in page.url:
        raise AssertionError("Staging Django superuser browser login unsuccessful")
    print("PASS real staging Django superuser browser session", flush=True)
    response = page.goto(BACKEND + "/admin/content/announcement/", wait_until="domcontentloaded", timeout=35000)
    check_status(response, {200}, "superuser marketing administration")
    if page.locator("body").inner_text().lower().find("announcement") < 0:
        raise AssertionError("Announcement admin did not render")
    print("PASS Django superuser rendered protected announcement administration", flush=True)
    context.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--authenticated", action="store_true")
    args = parser.parse_args()
    assert_staging_only()
    if args.authenticated and os.environ.get("STAGING_AUTH_BROWSER_ACCEPTANCE") != "true":
        raise RuntimeError("BLOCK: explicit staging browser acceptance is not enabled")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            public_browser(browser)
            if args.authenticated:
                authenticated_tutor(browser)
                authenticated_superuser(browser)
                print("PASS genuine staging browser tutor and superuser authentication", flush=True)
            else:
                print("NOT TESTED: authenticated tutor/admin browser sessions (secrets and fixtures required)", flush=True)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
