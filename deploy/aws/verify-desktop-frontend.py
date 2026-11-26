"""Verify desktop menu operation on the released AWS frontend."""
import os
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.environ["AMARIS_E2E_ROOT"])
os.environ["E2E_BASE_URL"] = os.environ["AMARIS_SITEWIDE_ORIGIN"]
from private_synthetic_responsive import check_current_navigation

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=os.environ["AMARIS_CHROME_PATH"])
    try:
        for width, height in ((1280, 480), (1366, 768), (2560, 1440)):
            page = browser.new_page(viewport={"width": width, "height": height}, reduced_motion="reduce")
            try:
                check_current_navigation(page)
                print(f"Live desktop menu passed at {width} × {height}.", flush=True)
            except Exception:
                state = page.evaluate("""() => ({
                    document: document.readyState,
                    controls: document.documentElement.dataset.amarisHeaderControls,
                    open: Array.from(document.querySelectorAll('.header-group')).map(menu => menu.open),
                    focus: document.activeElement?.tagName,
                })""")
                print(f"Desktop menu diagnostics at {width} × {height}: {state}", flush=True)
                raise
            finally:
                page.close()
    finally:
        browser.close()
