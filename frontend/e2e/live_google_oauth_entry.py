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
        print("NOT TESTED: Google credentials/consent, PKCE callback, verified student dashboard", flush=True)
        page.close()
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
