"""UI acceptance using synthetic fixtures and the actual chart component only."""

import json
import os
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

base = os.environ.get("ANALYTICS_PREVIEW_URL", "http://127.0.0.1:4173")
artifacts = Path("artifacts/analytics")
artifacts.mkdir(parents=True, exist_ok=True)
results = []

with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    for role in ("student", "tutor"):
        for width in (320, 390, 834, 1440):
            context = browser.new_context(viewport={"width": width, "height": 1000}, accept_downloads=True)
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            path = "/dashboard/analytics" if role == "student" else "/tutor/analytics"
            page.goto(f"{base}{path}/?days=30", wait_until="networkidle")
            page.get_by_role("heading", name="Make your progress visible.").wait_for()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), f"Page overflow at {width}"
            page.get_by_role("button", name="Bar", exact=True).click()
            assert page.get_by_role("button", name="Bar", exact=True).get_attribute("aria-pressed") == "true"
            page.get_by_role("button", name="Pie", exact=True).click()
            page.get_by_role("img", name=re.compile("contribution by service")).wait_for()
            page.get_by_role("button", name="Gauge", exact=True).click()
            page.get_by_placeholder("Enter your target").fill("10000")
            page.get_by_role("button", name="Save target", exact=True).click()
            page.get_by_role("img", name=re.compile("your personal target")).wait_for()
            page.reload(wait_until="networkidle")
            assert page.get_by_role("button", name="Gauge", exact=True).get_attribute("aria-pressed") == "true"
            page.get_by_role("img", name=re.compile("your personal target")).wait_for()
            page.get_by_role("button", name="Line", exact=True).click()
            page.get_by_text("View the exact daily data", exact=True).click()
            assert page.get_by_role("table").is_visible()
            with page.expect_download() as download:
                page.get_by_role("button", name="Export CSV", exact=True).click()
            file = artifacts / f"{role}-{width}.csv"
            download.value.save_as(file)
            content = file.read_text(encoding="utf-8-sig")
            assert '"Metric","Date / category","Value","Unit"' in content
            assert not any(value in content for value in ("access_token", "student_email", "bank_account"))
            page.get_by_text("View the exact daily data", exact=True).click()
            page.add_script_tag(path="node_modules/axe-core/axe.min.js")
            violations = page.evaluate("""async () => (await axe.run(document, {runOnly: {type:'tag',values:['wcag2a','wcag2aa','wcag21aa','wcag22aa']}})).violations""")
            assert not violations, json.dumps(violations)
            page.screenshot(path=str(artifacts / f"{role}-{width}.png"), full_page=True)
            page.get_by_role("link", name="7 days", exact=True).click()
            page.get_by_role("heading", name="Make your progress visible.").wait_for()
            assert page.get_by_role("link", name="7 days", exact=True).get_attribute("aria-current") == "page"
            assert not errors, errors
            results.append({"role": role, "width": width, "charts": 4, "csv": "pass", "persistence": "pass", "axe_violations": 0, "overflow": False})
            context.close()
    browser.close()
(artifacts / "results.json").write_text(json.dumps({"synthetic_fixture_only": True, "checks": results}, indent=2))
print(f"PASS: {len(results)} role/viewport combinations; chart selection, targets, persistence, CSV and accessibility.")
