"""Private-route responsive smoke with development-only synthetic identity.

Does not submit forms, create bookings, send messages or run PayFast.
Tests student dashboard/alerts, booking, video requests, invoice table, course
enrolment entry, payment recovery, lesson summary and navigation.
"""
from __future__ import annotations

import os
from pathlib import Path

import responsive_browser as suite
from playwright.sync_api import expect, sync_playwright


def check_current_navigation(page):
    suite.goto(page, "/")
    page.get_by_role("link", name="Amaris Mathematics Academy home").wait_for(state="visible", timeout=10_000)
    compact = page.viewport_size["width"] < 1280
    if compact:
        panel = page.locator(".header-mobile-menu")
        panel.locator("summary.header-mobile-trigger").click()
        nav = page.get_by_role("navigation", name="Mobile navigation")
        group = nav.locator("details.header-mobile-group").filter(
            has=page.locator("summary", has_text="Learn")
        ).first
    else:
        nav = page.get_by_role("navigation", name="Main navigation")
        nav.wait_for(state="visible")
        expect(page.locator("html")).to_have_attribute("data-amaris-header-controls", "ready")
        for menu in nav.locator("details.header-group").all():
            trigger = menu.locator("summary")
            trigger.press("Enter")
            dropdown = menu.locator(".header-dropdown")
            box = dropdown.bounding_box()
            viewport = page.viewport_size
            suite.require(
                box and box["x"] >= 0 and box["x"] + box["width"] <= viewport["width"]
                and box["y"] + box["height"] <= viewport["height"],
                f"{trigger.inner_text()} menu exceeds the viewport: {box} at {viewport}",
            )
            links = dropdown.get_by_role("link")
            for link in links.all():
                page.keyboard.press("Tab")
                expect(link).to_be_focused()
            # Allow subpixel rounding at the bottom edge of the scroll container.
            expect(links.last).to_be_in_viewport(ratio=0.99)
            links.last.press("Escape")
            expect(menu).to_have_js_property("open", False)
            expect(dropdown).to_be_hidden()
            expect(trigger).to_be_focused()
        group = nav.locator("details.header-group").filter(
            has=page.locator("summary", has_text="Learn")
        ).first
    suite.require(group.count() == 1, "Learn group missing")
    group.locator("summary").click()
    courses = group.locator('a[href="/courses"]')
    suite.require(courses.count() == 1 and courses.is_visible(), "Courses link missing from Learn menu")
    courses.focus()
    suite.require(courses.evaluate("(el) => document.activeElement === el"),
                  "Courses link cannot receive keyboard focus")
    suite.assert_no_horizontal_overflow(page, "site navigation")


def check_booking_form(page):
    suite.goto(page, "/book-online-live-class")
    expect(page.get_by_role("heading", name="Available Zoom slots")).to_be_visible()
    expect(page.get_by_role("combobox", name="Programme", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Show available tutor times")).to_be_visible()


def check_video_request_form(page):
    suite.goto(page, "/request-a-video")
    expect(page.get_by_role("combobox", name="Video package")).to_be_visible()
    expect(page.get_by_label("Supporting documents (optional)", exact=False)).to_be_visible()
    expect(page.get_by_role("button", name="Review secure payment")).to_be_visible()


CASE_NAMES = (
    ("navigation", check_current_navigation),
    ("dashboard", suite.check_dashboard),
    ("booking-form", check_booking_form),
    ("video-request-form", check_video_request_form),
    ("document-invoice", suite.check_table),
    ("checkout-and-payment-recovery", suite.check_checkout),
    ("lesson-course-structure", suite.check_lesson_interface),
)
SCREENSHOTS = Path("artifacts/sitewide-private-responsive")


def main():
    if os.environ.get("NODE_ENV") != "development":
        raise AssertionError("Only development-only synthetic sessions may be used")
    if os.environ.get("E2E_SYNTHETIC_STUDENT") != "true":
        raise AssertionError("Synthetic identity explicitly required")
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    errors = []
    count = 0
    viewports = {
        **suite.VIEWPORTS,
        "short-desktop-window": {"width": 1280, "height": 480},
        "compact-laptop": {"width": 1280, "height": 720},
        "laptop": {"width": 1366, "height": 768},
        "full-hd": {"width": 1920, "height": 1080},
        "wide-desktop": {"width": 2560, "height": 1440},
    }
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=os.getenv("AMARIS_CHROME_PATH") or None,
            headless=True, args=["--no-sandbox"],
        )
        try:
            for name, viewport in viewports.items():
                ctx = browser.new_context(
                    viewport=viewport,
                    locale="en-ZA", timezone_id="Africa/Johannesburg",
                    reduced_motion="reduce",
                )
                page = ctx.new_page()
                page.set_default_timeout(10_000)
                for label, fn in CASE_NAMES:
                    try:
                        fn(page)
                        suite.assert_no_horizontal_overflow(page, label + " " + name)
                        count += 1
                        print("PASS synthetic", name, label, flush=True)
                    except Exception as exc:
                        msg = f"{name}/{label}: {type(exc).__name__}: {exc}"
                        errors.append(msg)
                        print("FAIL synthetic", msg, flush=True)
                        try:
                            page.screenshot(
                                path=str(SCREENSHOTS / f"fail-{name}-{label}.png"),
                                full_page=True,
                            )
                        except Exception:
                            pass
                ctx.close()
        finally:
            browser.close()
    print(f"Private synthetic screen checks: {count}/{len(CASE_NAMES) * len(viewports)}")
    if errors:
        raise AssertionError("; ".join(errors))
    print("PASS all synthetic student private screen checks")


if __name__ == "__main__":
    main()
