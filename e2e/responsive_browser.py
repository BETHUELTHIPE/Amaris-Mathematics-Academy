from __future__ import annotations

import os
import re
import sys
import traceback
from pathlib import Path

from playwright.sync_api import Browser, Page, sync_playwright

BASE_URL = os.getenv("E2E_BASE_URL", "http://127.0.0.1:3000").rstrip("/")
ARTIFACT_DIR = Path(os.getenv("E2E_ARTIFACT_DIR", "artifacts/e2e"))
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

VIEWPORTS = {
    "mobile": {"width": 390, "height": 844},
    "tablet": {"width": 834, "height": 1112},
    "desktop": {"width": 1440, "height": 1000},
}

COURSE_PATH = "/courses/caps-grade-12-mathematics"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def goto(page: Page, path: str) -> None:
    response = page.goto(f"{BASE_URL}{path}", wait_until="domcontentloaded", timeout=30_000)
    require(response is not None, f"No HTTP response for {path}")
    require(response.status < 400, f"{path} returned HTTP {response.status}")
    page.wait_for_timeout(150)


def assert_no_horizontal_overflow(page: Page, surface: str) -> None:
    metrics = page.evaluate(
        """() => ({
          viewport: window.innerWidth,
          documentWidth: document.documentElement.scrollWidth,
          bodyWidth: document.body.scrollWidth,
        })"""
    )
    widest = max(metrics["documentWidth"], metrics["bodyWidth"])
    require(
        widest <= metrics["viewport"] + 2,
        f"{surface} overflows horizontally: viewport={metrics['viewport']} content={widest}",
    )


def check_navigation(page: Page, viewport_name: str) -> None:
    goto(page, "/")
    require(page.get_by_role("link", name="Amaris Mathematics Academy home").is_visible(), "Home link is not visible")
    if viewport_name in {"mobile", "tablet"}:
        menu = page.locator("summary").filter(has_text="Menu")
        require(menu.is_visible(), f"Compact navigation menu is missing on {viewport_name}")
        menu.click()
        courses = page.locator('details a[href="/courses"]').first
        require(courses.is_visible(), f"Courses navigation is not available from the {viewport_name} menu")
    else:
        navigation = page.get_by_role("navigation", name="Main navigation")
        require(navigation.is_visible(), "Desktop main navigation is not visible")
        require(navigation.get_by_role("link", name="Courses").is_visible(), "Desktop Courses link is not visible")
    assert_no_horizontal_overflow(page, "navigation")


def check_form(page: Page) -> None:
    goto(page, "/contact")
    page.locator("#fullName").fill("Responsive Test Student")
    page.locator("#email").fill("responsive.student@example.test")
    page.locator("#phone").fill("0710000000")
    page.locator("#enquiryType").select_option("technical-support")
    page.locator("#message").fill("Synthetic responsive browser test message with sufficient safe detail.")
    checkbox = page.locator("#consent")
    checkbox.click()

    require(page.locator("#fullName").input_value() == "Responsive Test Student", "Full-name field did not retain its value")
    require(page.locator("#email").input_value() == "responsive.student@example.test", "Email field did not retain its value")
    require(page.locator("#enquiryType").input_value() == "technical-support", "Enquiry type was not selected")
    require(checkbox.get_attribute("aria-checked") == "true", "Consent checkbox was not selected")
    require(page.get_by_role("button", name=re.compile("Send enquiry")).is_visible(), "Enquiry submit button is not visible")
    assert_no_horizontal_overflow(page, "enquiry form")


def check_dashboard(page: Page) -> None:
    goto(page, "/dashboard")
    require(page.get_by_text("Student dashboard", exact=True).is_visible(), "Student dashboard label is not visible")
    require(page.get_by_role("heading", name=re.compile(r"Welcome, Responsive\.")).is_visible(), "Synthetic student dashboard did not render")
    require(page.get_by_role("navigation", name="Dashboard navigation").is_visible(), "Dashboard navigation is not visible")
    require(page.get_by_text("Your course shelf is waiting.", exact=True).is_visible(), "Dashboard course shelf is not visible")
    assert_no_horizontal_overflow(page, "dashboard")


def check_table(page: Page) -> None:
    goto(page, "/documents/invoice")
    table = page.get_by_role("table")
    require(table.is_visible(), "Invoice table is not visible")
    for heading in ("Description", "Qty", "Unit price", "Amount"):
        require(page.get_by_role("columnheader", name=heading).is_visible(), f"Invoice column {heading!r} is not visible")
    require(page.get_by_text("Mathematics course enrolment", exact=True).is_visible(), "Invoice line item is not visible")
    assert_no_horizontal_overflow(page, "invoice table")


def check_checkout(page: Page) -> None:
    goto(page, COURSE_PATH)
    require(page.get_by_text("Complete course access", exact=True).is_visible(), "Checkout entry card is not visible")
    require(page.get_by_text(re.compile("secure PayFast checkout", re.IGNORECASE)).first.is_visible(), "PayFast checkout guidance is not visible")
    cta = page.get_by_role("link", name=re.compile("Continue to enrol"))
    require(cta.is_visible(), "Verified-student checkout CTA is not visible")
    require(cta.get_attribute("href") == "/dashboard", "Checkout entry CTA does not return the verified student to the dashboard")

    goto(page, "/payments/pending")
    require(
        page.get_by_role("heading", name="Your payment is still being confirmed.").is_visible(),
        "Payment-pending recovery state is not visible",
    )
    require(page.get_by_text(re.compile("Please do not pay again", re.IGNORECASE)).is_visible(), "Duplicate-payment warning is not visible")
    assert_no_horizontal_overflow(page, "checkout/payment state")


def check_lesson_interface(page: Page) -> None:
    goto(page, COURSE_PATH)
    require(page.get_by_text("Course structure", exact=True).is_visible(), "Course structure is not visible")
    require(page.get_by_text("Algebra & equations", exact=True).is_visible(), "Representative lesson/module item is not visible")
    require(
        page.get_by_text("Video explanation · worked examples · practice", exact=True).first.is_visible(),
        "Lesson delivery summary is not visible",
    )
    assert_no_horizontal_overflow(page, "lesson/course structure")


CHECKS = (
    ("navigation", check_navigation),
    ("forms", check_form),
    ("dashboard", check_dashboard),
    ("tables", check_table),
    ("checkout", check_checkout),
    ("lesson-interface", check_lesson_interface),
)


def run_context(browser: Browser, engine_name: str, viewport_name: str, viewport: dict[str, int]) -> list[str]:
    failures: list[str] = []
    context = browser.new_context(
        viewport=viewport,
        locale="en-ZA",
        timezone_id="Africa/Johannesburg",
        reduced_motion="reduce",
    )
    page = context.new_page()
    page.set_default_timeout(10_000)

    for check_name, check in CHECKS:
        try:
            if check_name == "navigation":
                check(page, viewport_name)
            else:
                check(page)
            print(f"PASS {engine_name:8} {viewport_name:7} {check_name}")
        except Exception as exc:  # noqa: BLE001 - aggregate all browser failures before exiting
            screenshot = ARTIFACT_DIR / f"{engine_name}-{viewport_name}-{check_name}.png"
            try:
                page.screenshot(path=str(screenshot), full_page=True)
            except Exception:
                pass
            failures.append(f"{engine_name}/{viewport_name}/{check_name}: {exc}")
            print(f"FAIL {engine_name:8} {viewport_name:7} {check_name}: {exc}", file=sys.stderr)
            traceback.print_exc()

    context.close()
    return failures


def main() -> int:
    failures: list[str] = []
    with sync_playwright() as playwright:
        for engine_name in ("chromium", "firefox", "webkit"):
            browser_type = getattr(playwright, engine_name)
            browser = browser_type.launch(headless=True)
            try:
                for viewport_name, viewport in VIEWPORTS.items():
                    failures.extend(run_context(browser, engine_name, viewport_name, viewport))
            finally:
                browser.close()

    total = 3 * len(VIEWPORTS) * len(CHECKS)
    passed = total - len(failures)
    print(f"\nResponsive/browser checks: {passed}/{total} passed")
    if failures:
        print("\nFailures:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
