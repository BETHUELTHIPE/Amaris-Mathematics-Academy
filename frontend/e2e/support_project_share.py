"""Synthetic browser checks for the public Support Our Project share controls.

Never submits contributions or contacts the payment provider.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

FRONTEND = Path(__file__).resolve().parents[1]
LOCAL = "http://127.0.0.1:4319"
PUBLIC = "https://amaris-mathematics-academy-live-students.onrender.com/support-our-project"


def wait_for_render(process):
    for _ in range(70):
        if process.poll() is not None:
            raise RuntimeError(f"Nitro server exited with {process.returncode}")
        try:
            with urlopen(LOCAL + "/support-our-project", timeout=3) as response:
                if response.status == 200:
                    return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("Support page did not become ready")


def main():
    with open("/tmp/amaris-support-project-share.log", "w", encoding="utf-8") as logfile:
        proc = subprocess.Popen(
            ["node", ".output/server/index.mjs"],
            cwd=FRONTEND,
            env={**os.environ, "HOST": "127.0.0.1", "PORT": "4319",
                 "NITRO_PORT": "4319", "NODE_ENV": "production", "CMS_API_URL": ""},
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
                      value: async (data) => { window.__projectShare = data; }
                    });
                """)
                page = mobile.new_page()
                response = page.goto(LOCAL + "/support-our-project", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.get_by_role("heading", name="Share this project with someone who could help.").wait_for()
                assert page.locator("#amaris-support-share-url").input_value() == PUBLIC
                assert page.locator('link[rel="canonical"]').get_attribute("href") == PUBLIC
                assert page.locator('meta[property="og:url"]').get_attribute("content") == PUBLIC
                page.get_by_role("button", name="Share project").click()
                page.wait_for_function("window.__projectShare?.url !== undefined")
                shared = page.evaluate("window.__projectShare")
                assert shared["url"] == PUBLIC
                page.get_by_role("button", name="Copy link").click()
                page.get_by_text("Support Our Project link copied.", exact=False).wait_for()
                copied = page.evaluate("navigator.clipboard.readText()")
                assert copied == PUBLIC
                whatsapp = page.locator('a[href^="https://wa.me/?text="]')
                assert "wa.me/?text=" in whatsapp.get_attribute("href")
                assert "support-our-project" in whatsapp.get_attribute("href")
                print("PASS mobile native share, clipboard, WhatsApp and canonical link", flush=True)
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
                fallback.goto(LOCAL + "/support-our-project", wait_until="domcontentloaded")
                fallback.get_by_role("button", name="Copy link").click()
                fallback.get_by_text("Select the link above and copy it", exact=False).wait_for()
                assert fallback.locator("#amaris-support-share-url").input_value() == PUBLIC
                assert fallback.locator("#amaris-support-share-url").evaluate("(el) => document.activeElement === el")
                assert fallback.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 2")
                print("PASS 320px manual copy fallback and no horizontal overflow", flush=True)
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
