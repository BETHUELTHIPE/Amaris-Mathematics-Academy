"""Read-only live Google OAuth entrance test; never automates a Google account login.

This checks a fresh anonymous browser on Render, a protected dashboard redirect,
and that the Google sign-in button initiates a real Google OAuth flow. It CANNOT
prove authenticated access: that requires a human-authorized Google sign-in.
"""
import json
import os
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

ORIGIN = "https://amaris-mathematics-academy-live-students.onrender.com"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=os.getenv("AMARIS_CHROME_PATH") or None,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            is_mobile=True,
            has_touch=True,
        )
        page = context.new_page()
        response = page.goto(ORIGIN + "/login", wait_until="domcontentloaded", timeout=90000)
        if response is None or response.status != 200:
            raise AssertionError("FAIL public login page not HTTP 200")
        page.get_by_role("button", name="Sign in with Google").wait_for(timeout=20000)
        page.get_by_label("Email address").wait_for(timeout=20000)
        print("PASS live login shows genuine Google sign-in and alternative email login", flush=True)

        auth_state = page.request.get(ORIGIN + "/api/auth-state", timeout=30000)
        state = auth_state.json()
        if auth_state.status != 200 or state.get("authenticated") is not False:
            raise AssertionError("FAIL anonymous auth-state API did not report unauthenticated")
        print("PASS fresh browser is unauthenticated (no fabricated student session)", flush=True)

        page.goto(ORIGIN + "/dashboard", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_url("**/login?next=*", timeout=20000)
        if not page.url.startswith(ORIGIN + "/login?next="):
            raise AssertionError("FAIL unauthenticated dashboard request not redirected to login")
        print("PASS dashboard rejects fresh anonymous visitor and preserves return path", flush=True)

        google = page.get_by_role("button", name="Sign in with Google")
        google.click(timeout=20000)
        try:
            page.wait_for_url(
                lambda u: urlsplit(str(u)).hostname in {
                    "accounts.google.com",
                    "accounts.youtube.com",
                },
                timeout=45000,
            )
        except Exception as exc:
            # Never log OAuth codes, state values or sensitive URL query strings.
            host = urlsplit(page.url).hostname or "unknown"
            raise AssertionError(f"FAIL Google provider page not reached (current host {host})") from exc

        print("PASS live Google button initiated OAuth and navigated to accounts.google.com", flush=True)

        # Confirm the new-student registration route also starts OAuth, not
        # merely the returning student's /login page.
        registration_context = browser.new_context(
            viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
        )
        registration_page = registration_context.new_page()
        registration_response = registration_page.goto(
            ORIGIN + "/register", wait_until="domcontentloaded", timeout=90000
        )
        if registration_response is None or registration_response.status != 200:
            raise AssertionError("FAIL new-student registration page not HTTP 200")
        registration_page.get_by_role("button", name="Register with Google").wait_for(timeout=20000)
        registration_page.get_by_role("button", name="Create student profile").wait_for(timeout=20000)
        print("PASS live registration displays Google and email enrolment options", flush=True)

        registration_page.get_by_role("button", name="Register with Google").click(timeout=20000)
        try:
            registration_page.wait_for_url(
                lambda u: urlsplit(str(u)).hostname in {
                    "accounts.google.com", "accounts.youtube.com"
                },
                timeout=45000,
            )
        except Exception as exc:
            host = urlsplit(registration_page.url).hostname or "unknown"
            raise AssertionError(
                f"FAIL Google registration provider page not reached (host {host})"
            ) from exc
        print("PASS live Register with Google reached Google OAuth provider", flush=True)

        # Never exchange a real Google OAuth code here; missing-code callbacks
        # must fail closed and never fabricate a session.
        callback = registration_page.request.get(
            ORIGIN + "/auth/callback", max_redirects=0, timeout=30000
        )
        if callback.status not in (302, 303, 307, 308):
            raise AssertionError("FAIL missing-code OAuth callback not redirected")
        destination = urlsplit(callback.headers.get("location", ""))
        if destination.hostname != urlsplit(ORIGIN).hostname or destination.path != "/login":
            raise AssertionError("FAIL OAuth callback error did not return to safe login")
        print("PASS missing-code OAuth callback fails closed to student login", flush=True)
        registration_context.close()
        print("NOT TESTED: Google credentials/consent, PKCE callback, verified student dashboard", flush=True)
        page.close()
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
