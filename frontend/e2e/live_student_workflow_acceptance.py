"""Production student dashboard browser acceptance using a dedicated TEST-ONLY account.

Never run with a staff account or a student's personal login. Credentials are
obtained solely from protected GitHub Actions secrets. Captured images mask
private student content; the script never prints credentials or invoice details.
"""

from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright

LIVE_URL = "https://amaris-mathematics-academy-live-students.onrender.com"
OUT = Path("artifacts/live-student-dashboard")
OUT.mkdir(parents=True, exist_ok=True)
VIEWPORTS = {
    "mobile": {"width": 390, "height": 844},
    "tablet": {"width": 834, "height": 1112},
    "desktop": {"width": 1440, "height": 900},
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    email = os.environ.get("AMARIS_LIVE_TEST_STUDENT_EMAIL", "").strip()
    password = os.environ.get("AMARIS_LIVE_TEST_STUDENT_PASSWORD", "")
    require(bool(email and password), "Dedicated verified test-student login secrets are not configured.")
    require(email.lower().endswith(".test") is False, "Use a real verified dedicated Supabase test account.")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport=VIEWPORTS["desktop"],
            locale="en-ZA",
            timezone_id="Africa/Johannesburg",
            reduced_motion="reduce",
        )
        page = context.new_page()
        page.set_default_timeout(20_000)
        try:
            health = page.request.get(LIVE_URL + "/health/ready/", timeout=20_000)
            require(health.status == 200, "Render live frontend health check failed.")
            response = page.goto(LIVE_URL + "/login?next=%2Fdashboard", wait_until="domcontentloaded")
            require(response is not None and response.status < 400, "Student login page is unavailable.")
            page.locator('input[name="email"]').fill(email)
            page.locator('input[name="password"]').fill(password)
            page.get_by_role("button", name="Log in securely").click()
            page.wait_for_url("**/dashboard", timeout=35_000)
            page.get_by_role("heading", name="My learning workflows").wait_for(state="visible", timeout=20_000)

            for name, size in VIEWPORTS.items():
                page.set_viewport_size(size)
                page.get_by_role("heading", name="My learning workflows").wait_for(state="visible")
                nav = page.get_by_role("navigation", name="Dashboard navigation")
                require(nav.get_by_role("link", name="My workflows").is_visible(), "Workflow tab is hidden.")
                panel = page.locator("#my-workflows")
                require(panel.is_visible(), "Workflow panel is missing.")
                require(not panel.get_by_text("Workflow status is temporarily unavailable.").count(), "Authenticated student API unavailable.")
                metrics = page.evaluate("""() => ({
                    viewport: window.innerWidth,
                    content: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
                })""")
                require(metrics["content"] <= metrics["viewport"] + 2, "Student page overflows horizontally.")

                # Mask all per-student cards and any visible identity before saving.
                page.screenshot(
                    path=str(OUT / (name + "-redacted.png")),
                    full_page=True,
                    mask=[
                        page.locator("#my-workflows article"),
                        page.locator("#my-workflows [role=progressbar]").locator(".."),
                        page.locator("h1"),
                    ],
                )
                print("PASS production verified-student workflow UI: " + name, flush=True)

            page.get_by_role("button", name="Refresh my workflow progress").click()
            page.get_by_role("heading", name="My learning workflows").wait_for(state="visible")
            page.reload(wait_until="domcontentloaded")
            page.get_by_role("heading", name="My learning workflows").wait_for(state="visible")
            print("PASS production session persisted, workflow refresh functional", flush=True)
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
