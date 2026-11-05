"""Genuine production tutor login acceptance: read-only and redacted.

Uses only a dedicated, verified and Django-approved tutor TEST account.
Protected GitHub environment secrets are required; no browser storage dumps,
HAR traces, account names, email addresses or financial values are recorded.
"""
from __future__ import annotations

import os

from playwright.sync_api import sync_playwright

URL = "https://amaris-mathematics-academy-live-students.onrender.com"


def verify(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    email = os.environ.get("AMARIS_LIVE_TEST_TUTOR_EMAIL", "").strip()
    password = os.environ.get("AMARIS_LIVE_TEST_TUTOR_PASSWORD", "")
    verify(bool(email and password), "BLOCK: dedicated tutor test credentials missing in protected GitHub environment")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            locale="en-ZA", timezone_id="Africa/Johannesburg",
            reduced_motion="reduce",
        )
        page = context.new_page()
        page.set_default_timeout(30_000)
        try:
            login = page.goto(URL + "/tutor/login", wait_until="domcontentloaded", timeout=45_000)
            verify(login is not None and login.status < 400, "Production tutor login page unavailable")
            page.locator('input[name="email"]').fill(email)
            page.locator('input[name="password"]').fill(password)
            page.get_by_role("button", name="Sign in to tutor dashboard").click()
            page.wait_for_url("**/tutor/dashboard", timeout=45_000)

            page.get_by_role("heading", name="Your teaching slots").wait_for(state="visible", timeout=45_000)
            page.get_by_role("heading", name="Offer a new live Zoom class").wait_for(state="visible")
            page.get_by_role("button", name="Publish tutor availability").wait_for(state="visible")
            verify(not page.get_by_text("Tutor service unavailable").count(), "Tutor dashboard API unavailable")
            verify(not page.get_by_text("Tutor access requires approval").count(), "Tutor role was not approved")
            print("PASS genuine approved tutor sign-in, timetable and availability form (read only)", flush=True)

            for width, height in [(390, 844), (1440, 900)]:
                page.set_viewport_size({"width": width, "height": height})
                dimensions = page.evaluate("""() => ({
                    w: innerWidth,
                    body: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
                })""")
                verify(dimensions["body"] <= dimensions["w"] + 2,
                       "Tutor dashboard has horizontal overflow on a verified session")
                print(f"PASS tutor dashboard layout at {width}px", flush=True)

            page.reload(wait_until="domcontentloaded")
            page.get_by_role("heading", name="Your teaching slots").wait_for(state="visible", timeout=45_000)
            print("PASS verified tutor session persists after reload", flush=True)
            # Do not submit an availability slot, payment, payout or booking.
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
