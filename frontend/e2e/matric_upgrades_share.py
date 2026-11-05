"""Public Matric Upgrades sharing: real headless Chromium, no account or payments."""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

FRONTEND = Path(__file__).resolve().parents[1]
LOCAL = "http://127.0.0.1:4323"
PUBLIC = "https://amaris-mathematics-academy-live-students.onrender.com/matric-upgrades"


def wait_for_render(process):
    for _ in range(70):
        if process.poll() is not None:
            raise RuntimeError(f"Nitro server exited with {process.returncode}")
        try:
            with urlopen(LOCAL + "/matric-upgrades", timeout=3) as response:
                if response.status == 200:
                    return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("Matric Upgrades page did not become ready")


def main():
    with open("/tmp/amaris-matric-share-browser.log", "w", encoding="utf-8") as logfile:
        proc = subprocess.Popen(
            ["node", ".output/server/index.mjs"],
            cwd=FRONTEND,
            env={**os.environ, "HOST": "127.0.0.1", "PORT": "4323",
                 "NITRO_PORT": "4323", "NODE_ENV": "production", "CMS_API_URL": ""},
            stdout=logfile, stderr=subprocess.STDOUT,
        )
        try:
            wait_for_render(proc)
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True, executable_path=os.getenv("CHROME_PATH") or None,
                    args=["--no-sandbox", "--disable-dev-shm-usage"]
                )
                mobile = browser.new_context(
                    viewport={"width": 390, "height": 844},
                    is_mobile=True, has_touch=True,
                    permissions=["clipboard-read", "clipboard-write"],
                )
                mobile.add_init_script("""
                    Object.defineProperty(navigator, 'share', {
                      configurable: true,
                      value: async (data) => { window.__matricShare = data; }
                    });
                """)
                page = mobile.new_page()
                response = page.goto(LOCAL + "/matric-upgrades?token=synthetic-ignored", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.get_by_role("heading", name="Know someone who wants to upgrade their matric?").wait_for()
                assert page.locator("#amaris-matric-share-url").input_value() == PUBLIC
                assert page.locator('link[rel="canonical"]').get_attribute("href") == PUBLIC
                assert page.locator('meta[property="og:url"]').get_attribute("content") == PUBLIC
                page.get_by_role("button", name="Share page").click()
                page.wait_for_function("window.__matricShare?.url !== undefined")
                shared = page.evaluate("window.__matricShare")
                assert shared["url"] == PUBLIC
                assert "synthetic-ignored" not in str(shared)
                page.get_by_role("button", name="Copy link").click()
                page.get_by_text("Matric Upgrades link copied.", exact=False).wait_for()
                assert page.evaluate("navigator.clipboard.readText()") == PUBLIC
                whatsapp = page.locator('a[href^="https://wa.me/?text="]')
                whatsapp_message = parse_qs(urlsplit(whatsapp.get_attribute("href")).query)["text"][0]
                assert PUBLIC in whatsapp_message
                assert "synthetic-ignored" not in whatsapp_message
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 2")
                print("PASS 390px native share, clipboard, WhatsApp, canonical and no private query leakage", flush=True)
                mobile.close()

                restricted = browser.new_context(viewport={"width": 320, "height": 720})
                restricted.add_init_script("""
                    Object.defineProperty(navigator, 'clipboard', {
                      configurable: true, get: () => undefined
                    });
                    Object.defineProperty(navigator, 'share', {
                      configurable: true, get: () => undefined
                    });
                """)
                fallback = restricted.new_page()
                fallback.goto(LOCAL + "/matric-upgrades", wait_until="domcontentloaded")
                fallback.get_by_role("button", name="Copy link").click()
                fallback.get_by_text("Select the link above and copy it", exact=False).wait_for()
                assert fallback.locator("#amaris-matric-share-url").input_value() == PUBLIC
                assert fallback.locator("#amaris-matric-share-url").evaluate("(el) => document.activeElement === el")
                assert fallback.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 2")
                print("PASS 320px manual copy fallback, input focus and no horizontal overflow", flush=True)
                restricted.close()
                browser.close()
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


if __name__ == "__main__":
    main()
