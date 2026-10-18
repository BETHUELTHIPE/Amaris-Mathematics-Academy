"""Browser acceptance of the authenticated synthetic workflow dashboard.

Runs only against a local development build with compile-time synthetic test
identity and fake student-scoped data. Never logs in to a production account or
attempts PayFast payments. The screenshots are intentionally fictitious.
"""

from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:3000").rstrip("/")
OUT = Path(os.environ.get("E2E_VISUAL_ARTIFACT_DIR", "artifacts/student-workflows"))
OUT.mkdir(parents=True, exist_ok=True)
AXE = Path("node_modules/axe-core/axe.min.js")

SIZES = {
    "narrow-mobile": {"width": 320, "height": 700},
    "mobile": {"width": 390, "height": 844},
    "tablet": {"width": 834, "height": 1112},
    "desktop": {"width": 1440, "height": 1000},
}


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run() -> None:
    check(AXE.is_file(), "Missing axe-core bundle: install frontend dependencies")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for name, viewport in SIZES.items():
                context = browser.new_context(
                    viewport=viewport,
                    locale="en-ZA",
                    timezone_id="Africa/Johannesburg",
                    reduced_motion="reduce",
                )
                page = context.new_page()
                page.set_default_timeout(15_000)
                try:
                    response = page.goto(BASE + "/dashboard", wait_until="domcontentloaded", timeout=30_000)
                    check(response is not None and response.status == 200, "Dashboard did not return HTTP 200")
                    page.get_by_role("heading", name="My learning workflows").wait_for(state="visible")
                    check(page.get_by_role("heading", name="Welcome, Responsive.").is_visible(), "Synthetic verified student was not authenticated")
                    check(page.locator("#my-workflows article").count() == 4, "Expected four synthetic student-owned workflows")
                    nav = page.get_by_role("navigation", name="Dashboard navigation")
                    link = nav.get_by_role("link", name="My workflows")
                    check(link.is_visible(), "Student workflow navigation is not visible")
                    check(link.get_attribute("href") == "/dashboard#my-workflows", "Workflow navigation target is wrong")

                    course = page.locator("#my-workflows article").filter(has_text="CAPS Grade 12 Mathematics — synthetic visual test")
                    live = page.locator("#my-workflows article").filter(has_text="Zoom Algebra Class — synthetic visual test")
                    review = page.locator("#my-workflows article").filter(has_text="Trigonometry video — synthetic visual test")
                    ready = page.locator("#my-workflows article").filter(has_text="Functions video — synthetic visual test")
                    for card in (course, live, review, ready):
                        check(card.count() == 1 and card.is_visible(), "One student workflow card is missing")

                    check("3 of 3 stages confirmed" in course.inner_text(), "Paid course access not correctly verified")
                    check("3 of 4 stages confirmed" in live.inner_text(), "Confirmed class falsely appears completed")
                    check("5 of 7 stages confirmed" in review.inner_text(), "Video under review falsely appears ready")
                    check("7 of 7 stages confirmed" in ready.inner_text(), "Completed video not shown as ready")
                    check(page.get_by_role("progressbar", name="CAPS Grade 12 Mathematics — synthetic visual test learning progress").get_attribute("aria-valuenow") == "63", "Course progress must come from synthetic record")
                    check(not page.get_by_text("temporarily unavailable").count(), "Synthetic workflow service falsely reported unavailable")

                    metrics = page.evaluate("""() => ({
                      viewport: window.innerWidth,
                      widest: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
                    })""")
                    check(metrics["widest"] <= metrics["viewport"] + 2, "Dashboard horizontally overflows at " + name)

                    page.add_script_tag(path=str(AXE))
                    report = page.evaluate("""async () => {
                      const element = document.querySelector('#my-workflows');
                      return axe.run(element, {
                        runOnly: {type: 'tag', values: ['wcag2a','wcag2aa','wcag21aa','wcag22aa']},
                        resultTypes: ['violations'],
                      });
                    }""")
                    violations = report.get("violations", [])
                    check(not violations, "Workflow WCAG violations: " + ", ".join(v.get("id", "?") for v in violations))

                    page.screenshot(path=str(OUT / (name + "-student-workflows.png")), full_page=True)

                    refresh = page.get_by_role("button", name="Refresh my workflow progress")
                    refresh.click()
                    page.get_by_role("heading", name="My learning workflows").wait_for(state="visible")
                    check(page.locator("#my-workflows article").count() == 4, "Refreshing lost workflow cards")
                    print("PASS " + name + " authenticated synthetic visual, workflow states, accessibility, refresh", flush=True)
                except Exception:
                    page.screenshot(path=str(OUT / (name + "-failure.png")), full_page=True)
                    raise
                finally:
                    context.close()
        finally:
            browser.close()


if __name__ == "__main__":
    run()
