"""Private-route responsive smoke with development-only synthetic identity.

Does not submit forms, create bookings, send messages or run PayFast.
Tests student dashboard/alerts, invoice table, course enrolment entry,
payment recovery, lesson summary, and mobile navigation at 4 widths.
"""
from __future__ import annotations

import os
from pathlib import Path

import responsive_browser as suite
from playwright.sync_api import sync_playwright

CASE_NAMES = (
    ("navigation", suite.check_navigation),
    ("dashboard", suite.check_dashboard),
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
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            for name, viewport in suite.VIEWPORTS.items():
                ctx = browser.new_context(
                    viewport=viewport,
                    locale="en-ZA", timezone_id="Africa/Johannesburg",
                    reduced_motion="reduce",
                )
                page = ctx.new_page()
                for label, fn in CASE_NAMES:
                    try:
                        if label == "navigation":
                            fn(page, name)
                        else:
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
    print(f"Private synthetic screen checks: {count}/{len(CASE_NAMES) * len(suite.VIEWPORTS)}")
    if errors:
        raise AssertionError("; ".join(errors))
    print("PASS all synthetic student private screen checks")


if __name__ == "__main__":
    main()
