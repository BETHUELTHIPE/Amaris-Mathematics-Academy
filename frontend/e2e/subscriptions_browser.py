"""Public subscription UX against the locally built Node application; no charges."""
import os
import shutil
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

BASE = os.getenv("SUBSCRIPTION_TEST_URL", "http://127.0.0.1:38122")
ROOT = Path(__file__).resolve().parents[1]


def main():
    if urlsplit(BASE).hostname not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("Use the isolated local subscription preview for this test.")
    for attempt in range(30):
        try:
            with urlopen(BASE + "/subscriptions", timeout=2) as response:
                if response.status == 200:
                    break
        except OSError:
            if attempt == 29:
                raise
            time.sleep(1)
    chrome = os.getenv("SUBSCRIPTION_CHROME_PATH") or shutil.which("chromium") or shutil.which("google-chrome")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=chrome, headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        page.set_default_timeout(30000)
        for width, height in [(320, 720), (390, 844), (768, 1024), (1440, 1000)]:
            page.set_viewport_size({"width": width, "height": height})
            page.goto(BASE, wait_until="networkidle")
            expect(page.locator("#course-subscriptions")).to_contain_text("R3,800")
            expect(page.locator("#course-subscriptions")).to_contain_text("R7,600")
            expect(page.locator("#course-subscriptions")).to_contain_text("Two 2-hour one-to-one Zoom sessions every week")
            expect(page.locator("#course-subscriptions")).to_contain_text("4 hours of one-to-one tutor support per week")
            expect(page.locator("#course-subscriptions")).to_contain_text("R950/month equivalent")
            for slug, price in [("4-months", "R3,800"), ("8-months", "R7,600")]:
                page.goto(BASE + "/subscriptions/" + slug, wait_until="networkidle")
                expect(page.get_by_role("heading", name="Choose your curriculum", exact=True)).to_be_visible()
                expect(page.get_by_text(price, exact=True)).to_be_visible()
                expect(page.locator("aside")).to_contain_text("Two 2-hour one-to-one Zoom sessions every week")
                expect(page.locator("aside")).to_contain_text("4 hours of one-to-one tutor support per week")
                expect(page.get_by_role("region", name="Your weekly learning rhythm")).to_contain_text("Understand it")
                expect(page.get_by_role("region", name="Your weekly learning rhythm")).to_contain_text("Put it into practice")
                radios = page.locator('input[name="curriculum"]')
                expect(radios).to_have_count(5)
                form = page.locator('form[action$="/checkout"]')
                assert not form.evaluate("form => form.checkValidity()")
                for value in ["caps", "ieb", "nated", "ncv", "university"]:
                    page.locator(f'input[value="{value}"]').check()
                    assert form.evaluate("form => form.checkValidity()")
                    expect(page.locator('input[name="curriculum"]:checked')).to_have_count(1)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
                page.add_script_tag(path=str(ROOT / "node_modules/axe-core/axe.min.js"))
                result = page.evaluate("async () => (await axe.run({include: ['main']}, {runOnly: {type:'tag', values:['wcag2a','wcag2aa','wcag21aa','wcag22aa']}})).violations.map(v=>({id:v.id,impact:v.impact}))")
                assert not result, result
                print(f"PASS {slug}: five required curriculum choices, price, layout and accessibility at {width}px")
                page.get_by_role("button", name="Continue with my curriculum").click()
                page.wait_for_url("**/login?next=**")
                next_page = parse_qs(urlsplit(page.url).query)["next"][0]
                assert next_page == f"/subscriptions/{slug}/checkout?curriculum=university", next_page
                print("PASS selected curriculum and plan preserved through verified sign-in gate")
        page.set_viewport_size({"width":1440,"height":1000})
        page.goto(BASE + "/subscriptions/4-months", wait_until="networkidle")
        page.screenshot(path="/tmp/amaris-subscription-desktop.png", full_page=True)
        browser.close()


if __name__ == "__main__":
    main()
