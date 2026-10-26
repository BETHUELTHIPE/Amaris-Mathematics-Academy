"""Staging-only REAL account dashboard identity acceptance.

Requires dedicated non-privileged QA student and Django-approved tutor accounts.
Never prints names, emails, passwords, sessions, tokens, or other private data.
Read-only: two genuine sign-ins, independent Supabase Auth identity reads, and
browser checks of the student and tutor private dashboards.
"""
from __future__ import annotations

import os
import re
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

FRONTEND = "https://amaris-mathematics-academy-staging-x4ax.onrender.com"
BACKEND = "https://amaris-mathematics-academy-staging.onrender.com"
AUTH = "https://atyhhjwwxgzeurnwayay.supabase.co"
PROJECT = "atyhhjwwxgzeurnwayay"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def secret(name: str) -> str:
    value = os.getenv(name, "")
    require(2 <= len(value) <= 4096 and not any(ch in value for ch in ("\r", "\n", "\x00")), "BLOCK: protected staging QA credential unavailable: " + name)
    return value


def expected_name(user: dict) -> str:
    metadata = user.get("user_metadata") or {}
    def clean(value):
        return value.strip()[:80] if isinstance(value, str) else ""
    full = clean(metadata.get("full_name")) or clean(metadata.get("name"))
    names = full.split()
    first = clean(metadata.get("first_name")) or clean(metadata.get("given_name")) or (names[0] if names else "")
    last = clean(metadata.get("last_name")) or clean(metadata.get("family_name")) or " ".join(names[1:])
    return " ".join(part for part in (first, last) if part) or "Name not provided"


def verify_provider_user(request, key: str, email: str, password: str) -> tuple[dict, str]:
    response = request.post(
        AUTH + "/auth/v1/token?grant_type=password",
        headers={"apikey": key, "Content-Type": "application/json"},
        data={"email": email, "password": password},
        timeout=45000,
    )
    if response.status != 200:
        # Only print allowlisted provider status codes, never the response body,
        # email address, bearer tokens, cookies, or password.
        try:
            code = response.json().get("error_code") or response.json().get("code") or ""
        except (ValueError, TypeError, AttributeError):
            code = ""
        safe = code if code in {"invalid_credentials", "email_not_confirmed", "over_request_rate_limit", "user_not_found", "unexpected_failure"} else "other"
        raise AssertionError(f"BLOCK: staging QA password auth HTTP {response.status}, reason {safe}")
    auth_data = response.json()
    token = auth_data.get("access_token")
    require(isinstance(token, str) and bool(token), "BLOCK: Supabase Auth did not issue QA access token")
    checked = request.get(AUTH + "/auth/v1/user",
                          headers={"apikey": key, "Authorization": "Bearer " + token},
                          timeout=40000)
    require(checked.status == 200, "BLOCK: authoritative Auth user lookup failed")
    user = checked.json()
    require(isinstance(user, dict) and user.get("email_confirmed_at") and
            user.get("email", "").strip().lower() == email, "BLOCK: test account email not confirmed or mismatched")
    return user, token


def verify_account_region(page, label: str, expected_email: str, expected_display_name: str) -> None:
    panel = page.get_by_role("region", name="Signed-in account")
    panel.wait_for(state="visible", timeout=45000)
    # Assert two independent fields EXACTLY, not a substring such as a booking student name.
    actual = panel.locator("p").all_inner_texts()
    require(len(actual) == 3 and actual[0].strip() == "Signed in as · " + label,
            "FAIL: role-specific private account heading incorrect")
    require(actual[1].strip() == expected_display_name,
            "FAIL: dashboard displayed name does not match authoritative account")
    require(actual[2].strip().lower() == expected_email,
            "FAIL: dashboard displayed email does not match authenticated account")
    require(expected_display_name != "Name not provided",
            "BLOCK: test account has no genuine full name metadata")
    require(len(expected_display_name.split()) >= 2,
            "BLOCK: account lacks a full first and last name; cannot certify full-name acceptance")


def main() -> None:
    require(os.getenv("GITHUB_REPOSITORY") == "BETHUELTHIPE/Amaris-Mathematics-Academy",
            "BLOCK: unexpected GitHub repository")
    require(os.getenv("GITHUB_REF") == "refs/heads/stage/dashboard-account-identity-acceptance-20261026",
            "BLOCK: only protected staging QA branch may run")
    key = secret("STAGING_SUPABASE_PUBLISHABLE_KEY")
    require(key.startswith("sb_publishable_") or key.count(".") == 2,
            "BLOCK: expected public staging Auth key")
    student_email = secret("STAGING_TEST_STUDENT_EMAIL").strip().lower()
    tutor_email = secret("STAGING_TEST_TUTOR_EMAIL").strip().lower()
    student_password = secret("STAGING_TEST_STUDENT_PASSWORD")
    tutor_password = secret("STAGING_TEST_TUTOR_PASSWORD")
    require("@" in student_email and "@" in tutor_email and student_email != tutor_email,
            "BLOCK: independent student and tutor QA identities required")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(viewport={"width": 1440, "height": 900},
                                      timezone_id="Africa/Johannesburg", locale="en-ZA")
        try:
            role = os.environ.get("AMARIS_STAGING_QA_ROLE", "").strip().lower()
            require(role in ("student", "tutor"), "BLOCK: explicit student or tutor acceptance role required")
            if role == "student":
                student, _ = verify_provider_user(context.request, key, student_email, student_password)
                student_name = expected_name(student)
                sctx = browser.new_context(viewport={"width": 1440, "height": 900})
                try:
                    student_page = sctx.new_page()
                    login_response = student_page.goto(FRONTEND + "/login", wait_until="domcontentloaded", timeout=45000)
                    login_path = urlsplit(student_page.url).path
                    require(login_response is not None and login_response.status == 200 and login_path == "/login",
                            f"BLOCK: student staging login page HTTP {login_response.status if login_response else 0}, path {login_path}")
                    require(student_page.locator('form:has(input[name="password"]) input[name="email"]').count() == 1,
                            "BLOCK: staging student password form unavailable")
                    student_page.locator('form:has(input[name="password"]) input[name="email"]').fill(student_email)
                    student_page.locator('form:has(input[name="password"]) input[name="password"]').fill(student_password)
                    student_page.get_by_role("button", name="Log in securely").click()
                    student_page.wait_for_url(re.compile(r"/dashboard(?:[/?]|$)"), timeout=45000)
                    for path in ("/dashboard", "/dashboard/orders", "/dashboard/notifications"):
                        response = student_page.goto(FRONTEND + path, wait_until="domcontentloaded", timeout=45000)
                        require(response is not None and response.status == 200,
                                "FAIL: verified student dashboard route unavailable")
                        verify_account_region(student_page, "Student", student_email, student_name)
                        print("PASS: real staging student identity on protected private dashboard (no PII logged)")
                finally:
                    sctx.close()

            else:
                tutor, tutor_token = verify_provider_user(context.request, key, tutor_email, tutor_password)
                tutor_name = expected_name(tutor)

                # Tutor fallback is permitted only when confirmed independently by an
                # authenticated Django-approved tutor API, never from user-provided UI.
                tutor_api = context.request.get(
                    BACKEND + "/api/v1/tutor/dashboard/",
                    headers={"Authorization": "Bearer " + tutor_token},
                    timeout=45000,
                )
                require(tutor_api.status == 200, "BLOCK: staging test tutor lacks Django Tutors approval")
                tutor_profile = tutor_api.json().get("tutor") or {}
                approved_tutor_name = tutor_profile.get("name")
                if tutor_name == "Name not provided":
                    require(isinstance(approved_tutor_name, str) and approved_tutor_name.strip(),
                            "BLOCK: approved tutor record missing a full name")
                    tutor_name = approved_tutor_name.strip()
                require(len(tutor_name.split()) >= 2,
                        "BLOCK: approved tutor full first and last name not supplied")
                require(tutor_profile.get("email", "").strip().lower() == tutor_email,
                        "BLOCK: Django tutor profile email differs from Supabase Auth")

                tctx = browser.new_context(viewport={"width": 1440, "height": 900})
                try:
                    tutor_page = tctx.new_page()
                    login_response = tutor_page.goto(FRONTEND + "/tutor/login", wait_until="domcontentloaded", timeout=45000)
                    login_path = urlsplit(tutor_page.url).path
                    require(login_response is not None and login_response.status == 200 and login_path == "/tutor/login",
                            f"BLOCK: tutor staging login page HTTP {login_response.status if login_response else 0}, path {login_path}")
                    require(tutor_page.locator('input[name="email"]').count() == 1,
                            "BLOCK: tutor email input unavailable on staging login page")
                    tutor_page.locator('input[name="email"]').fill(tutor_email)
                    tutor_page.locator('input[name="password"]').fill(tutor_password)
                    tutor_page.get_by_role("button", name="Sign in to tutor dashboard").click()
                    tutor_page.wait_for_url(re.compile(r"/tutor/dashboard(?:[/?]|$)"), timeout=45000)
                    tutor_page.get_by_role("heading", name="Your teaching slots").wait_for(state="visible", timeout=45000)
                    verify_account_region(tutor_page, "Tutor", tutor_email, tutor_name)
                    print("PASS: Django-approved staging tutor real account full name/email displayed (no PII logged)")
                finally:
                    tctx.close()

            print("PASS: real authenticated staging dashboard identity acceptance — " + role)
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
