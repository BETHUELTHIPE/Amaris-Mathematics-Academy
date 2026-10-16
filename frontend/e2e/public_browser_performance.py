"""Browser-level Amaris performance checks for the production-style Nitro build.

Anonymous public routes only, no student/payments or private credentials.
Captures LCP/CLS/long-task lab evidence at narrow mobile/tablet/desktop sizes.
"""
import json
import os
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "browser-performance"
ARTIFACTS.mkdir(parents=True, exist_ok=True)
ORIGIN = "http://127.0.0.1:3015"
SCRIPT = """
(() => {
  window.__amarisVitals = {cls: 0, lcpMs: 0, longTasks: 0};
  try {
    new PerformanceObserver(list => {
      for (const entry of list.getEntries()) {
        if (!entry.hadRecentInput) window.__amarisVitals.cls += entry.value;
      }
    }).observe({type: 'layout-shift', buffered: true});
  } catch {}
  try {
    new PerformanceObserver(list => {
      const records = list.getEntries();
      if (records.length) window.__amarisVitals.lcpMs = records.at(-1).startTime;
    }).observe({type: 'largest-contentful-paint', buffered: true});
  } catch {}
  try {
    new PerformanceObserver(list => {
      window.__amarisVitals.longTasks += list.getEntries().length;
    }).observe({type: 'longtask', buffered: true});
  } catch {}
})();
"""


def ready(server):
    for _ in range(65):
        if server.poll() is not None:
            raise RuntimeError(f"Nitro process exited ({server.returncode})")
        try:
            with urlopen(ORIGIN + "/", timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("Nitro server did not become ready")


def measure(browser, path, width, height, mobile):
    context = browser.new_context(
        viewport={"width": width, "height": height},
        is_mobile=mobile, has_touch=mobile, device_scale_factor=1,
        reduced_motion="reduce",
    )
    context.add_init_script(SCRIPT)
    page = context.new_page()
    page.goto(ORIGIN + path, wait_until="domcontentloaded", timeout=60000)
    page.locator("h1").first.wait_for(timeout=30000)
    page.wait_for_timeout(1700)
    before = page.evaluate("""() => ({
      documentWidth: document.documentElement.scrollWidth,
      windowWidth: window.innerWidth,
      ...window.__amarisVitals
    })""")
    # The lazy cards and cached contents must never push beyond the viewport.
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(650)
    after = page.evaluate("""() => ({
      documentWidth: document.documentElement.scrollWidth,
      windowWidth: window.innerWidth,
      ...window.__amarisVitals
    })""")
    label = path.strip("/") or "home"
    page.screenshot(path=str(ARTIFACTS / f"{label}-{width}.png"), full_page=True)
    if before["documentWidth"] > before["windowWidth"] + 2:
        raise AssertionError(f"horizontal overflow before scroll {path} {width}: {before}")
    if after["documentWidth"] > after["windowWidth"] + 2:
        raise AssertionError(f"horizontal overflow after scroll {path} {width}: {after}")
    if after["cls"] > 0.10:
        raise AssertionError(f"CLS above 0.10 in Chrome lab {path} {width}: {after['cls']}")
    if not after["lcpMs"] or after["lcpMs"] > 6000:
        raise AssertionError(f"missing or slow lab LCP {path} {width}: {after['lcpMs']}")
    record = {"page": path, "width": width, "mobile": mobile,
              "cls": round(after["cls"], 4), "lcpMs": round(after["lcpMs"]),
              "longTasks": after["longTasks"], "overflow": False}
    print("PASS browser", json.dumps(record, sort_keys=True), flush=True)
    context.close()
    return record


def main():
    with open(ARTIFACTS / "nitro.log", "w", encoding="utf-8") as log:
        server = subprocess.Popen(
            ["node", ".output/server/index.mjs"], cwd=ROOT,
            env={**os.environ, "HOST": "127.0.0.1", "PORT": "3015",
                 "NODE_ENV": "production", "CMS_API_URL": "",
                 "NITRO_PORT": "3015"},
            stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            ready(server)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    executable_path=os.getenv("AMARIS_CHROME_PATH") or None,
                    headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
                )
                results = []
                for path in ("/", "/courses", "/contact"):
                    for width, height, mobile in ((320, 720, True), (390, 844, True),
                                                   (768, 900, False), (1440, 900, False)):
                        results.append(measure(browser, path, width, height, mobile))
                browser.close()
                (ARTIFACTS / "metrics.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
                print("PASS all anonymous browser viewport/CLS/LCP checks", flush=True)
        finally:
            server.terminate()
            try:
                server.wait(timeout=8)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == "__main__":
    main()
