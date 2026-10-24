"""Site-wide responsive and accessibility gate, using only synthetic and anonymous requests.

Discover all Next.js app/page.tsx routes on every run. Dynamic routes use a
known-safe fixture URL; protected routes must redirect to login without a
student/tutor session. Never submit forms, make payments, invoke tutor actions,
or access real accounts. A separate authenticated synthetic suite is required
to validate the contents behind the login guard.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

FRONTEND = Path(__file__).resolve().parents[1]
APP = FRONTEND / "app"
ARTIFACTS = FRONTEND / "artifacts" / "sitewide-responsive"
ARTIFACTS.mkdir(parents=True, exist_ok=True)
BASE = "http://127.0.0.1:3027"
AXE = FRONTEND / "node_modules" / "axe-core" / "axe.min.js"
WIDTHS = ((320, 720), (390, 844), (768, 900), (1440, 900))
DYNAMIC = {
    "courses/[slug]": "/courses/caps-grade-12-mathematics",
    "checkout/[slug]": "/checkout/caps-grade-12-mathematics",
    "learn/[courseSlug]/[lessonSlug]": "/learn/caps-grade-12-mathematics/algebra-and-equations",
    "errors/[code]": "/errors/404",
}
GUARDED = ("/dashboard", "/checkout/", "/learn/", "/documents/", "/request-a-video/")
LOGIN_ROUTES = ("/login", "/verify-email", "/tutor/login", "/tutor/apply/login")
AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]
VITALS = """(() => {
  window.__siteWideCLS = 0;
  try {
    new PerformanceObserver(list => {
      for (const e of list.getEntries()) {
        if (!e.hadRecentInput) window.__siteWideCLS += e.value;
      }
    }).observe({type:'layout-shift', buffered:true});
  } catch {}
})();"""


def discover() -> list[tuple[str, str]]:
    found = []
    for source in sorted(APP.rglob("page.tsx")):
        subpath = str(source.relative_to(APP).parent).replace("\\", "/")
        route = "/" + subpath if subpath != "." else "/"
        if "[" in route:
            if subpath not in DYNAMIC:
                raise AssertionError(f"New dynamic route lacks a safe audit fixture: {route}")
            route = DYNAMIC[subpath]
        found.append((str(source.relative_to(FRONTEND)), route))
    if len(found) < 47:
        raise AssertionError(f"Expected at least 47 Next.js pages, got {len(found)}")
    if len({name for name, _ in found}) != len(found):
        raise AssertionError("Duplicate page source detected")
    print(f"DISCOVERED {len(found)} page routes", flush=True)
    return found


def ready(server):
    for _ in range(70):
        if server.poll() is not None:
            raise RuntimeError(f"Production-style Nitro process exited: {server.returncode}")
        try:
            with urlopen(BASE + "/", timeout=2) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            pass
        time.sleep(1)
    raise RuntimeError("Nitro server did not become ready")


def take_measurement(page):
    return page.evaluate("""() => ({
      width: innerWidth,
      root: document.documentElement.scrollWidth,
      body: document.body.scrollWidth,
      cls: window.__siteWideCLS || 0,
      viewportTag: Boolean(document.querySelector('meta[name="viewport"]')),
      headingCount: document.querySelectorAll('h1').length
    })""")


def record_page(page, source, path, width, height, scan_axe):
    response = page.goto(BASE + path, wait_until="domcontentloaded", timeout=25000)
    if response is None:
        raise AssertionError("No navigation response")
    if response.status >= 500:
        raise AssertionError(f"HTTP {response.status}: server failed")

    final = urlparse(page.url).path
    protected = path.startswith(GUARDED) or path == "/tutor/dashboard"
    if path == "/tutor/dashboard" and final not in LOGIN_ROUTES:
        # Server-rendered authentication can complete after DOMContentLoaded.
        # Wait for a verified denial, redirect, or actual private content.
        # A loading skeleton alone is NEVER accepted as proof of denial.
        try:
            page.wait_for_function(
                """() => {
                  const headings = [...document.querySelectorAll('h1')]
                    .map((node) => node.textContent || '');
                  const denied = headings.some((text) =>
                    text.includes('Tutor service unavailable')
                    || text.includes('Tutor access requires approval'));
                  const privateContent = document.body?.innerText.includes('Private tutor workspace');
                  return ['/login', '/verify-email', '/tutor/login', '/tutor/apply/login']
                    .includes(location.pathname) || denied || privateContent;
                }""",
                timeout=10000,
            )
        except Exception as error:
            raise AssertionError(
                "Anonymous tutor dashboard did not reach a verified denial within 10 seconds"
            ) from error
        final = urlparse(page.url).path
    if protected:
        if final not in LOGIN_ROUTES:
            # When the tutor backend is down, a safe, data-free error page is
            # acceptable. No private timetable or editable tutor controls may
            # be shown to an anonymous browser.
            safe_tutor_fallback = (
                path == "/tutor/dashboard"
                and final == "/tutor/dashboard"
                and (
                    page.get_by_role("heading", name="Tutor service unavailable").count()
                    or page.get_by_role("heading", name="Tutor access requires approval").count()
                )
                and page.get_by_text("Private tutor workspace").count() == 0
                and page.locator('form[action*="tutor"]').count() == 0
            )
            if not safe_tutor_fallback:
                raise AssertionError(
                    f"Protected route {path} leaked content or did not deny anonymous access: {final}"
                )
    elif response.status >= 400:
        raise AssertionError(f"Public route {path} returned HTTP {response.status}")

    page.wait_for_timeout(140)
    before = take_measurement(page)
    page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
    page.wait_for_timeout(180)
    after = take_measurement(page)
    maxwidth = max(before["root"], before["body"], after["root"], after["body"])
    if maxwidth > width + 2:
        raise AssertionError(f"Horizontal overflow {maxwidth}px on {width}px viewport ({final})")
    if after["cls"] > 0.10:
        raise AssertionError(f"CLS {after['cls']:.4f} exceeds 0.10 ({final}, {width}px)")
    if not after["viewportTag"]:
        raise AssertionError(f"Missing viewport meta tag on {final}")
    if after["headingCount"] < 1:
        raise AssertionError(f"No page heading on {final}")

    violations = []
    if scan_axe and AXE.exists():
        page.add_script_tag(path=str(AXE))
        violations = page.evaluate("""async tags => {
          const result = await axe.run(document, {
            runOnly: {type:'tag', values:tags},
            rules: {'color-contrast': {enabled:true}}
          });
          return result.violations
            .filter(v => v.impact === 'critical' || v.impact === 'serious')
            .map(v => ({id:v.id, impact:v.impact, count:v.nodes.length,
              targets:v.nodes.slice(0,2).map(n => n.target.join(' '))}));
        }""", AXE_TAGS)
        if violations:
            raise AssertionError(f"Serious axe issues on {final}: {json.dumps(violations)}")

    return {
        "source": source, "path": path, "renderedPath": final,
        "viewport": width, "status": response.status,
        "guarded": protected, "cls": round(after["cls"], 4),
        "overflow": False, "axeSerious": len(violations),
    }


def main():
    routes = discover()
    if not AXE.exists():
        raise RuntimeError("Install axe-core before running responsive audit")
    report = []
    failures = []
    with (ARTIFACTS / "nitro.log").open("w", encoding="utf-8") as log:
        server = subprocess.Popen(
            ["node", ".output/server/index.mjs"], cwd=FRONTEND,
            env={**os.environ, "NODE_ENV":"production",
                 "HOST":"127.0.0.1", "PORT":"3027", "NITRO_PORT":"3027",
                 "CMS_API_URL":""},
            stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            ready(server)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    executable_path=os.getenv("AMARIS_CHROME_PATH") or None,
                    headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                for width, height in WIDTHS:
                    context = browser.new_context(
                        viewport={"width":width, "height":height},
                        is_mobile=width < 600, has_touch=width < 600,
                        reduced_motion="reduce", locale="en-ZA",
                        timezone_id="Africa/Johannesburg",
                    )
                    context.add_init_script(VITALS)
                    page = context.new_page()
                    for source, path in routes:
                        try:
                            row = record_page(page, source, path, width, height, scan_axe=(width == 390))
                            report.append(row)
                            print(f"PASS {width:4} {path} -> {row['renderedPath']} "
                                  f"CLS={row['cls']}", flush=True)
                        except Exception as exc:
                            message = f"{width}px {path}: {type(exc).__name__}: {exc}"
                            failures.append(message)
                            print("FAIL " + message, flush=True)
                            safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", path).strip("_")[:70] or "home"
                            try:
                                page.screenshot(
                                    path=str(ARTIFACTS / f"failed-{width}-{safe}.png"),
                                    full_page=True, timeout=5000,
                                )
                            except Exception:
                                pass
                    context.close()
                browser.close()
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()

    (ARTIFACTS / "results.json").write_text(
        json.dumps({"routes":len(routes), "viewports":list(width for width, _ in WIDTHS),
                    "results":report,"failures":failures}, indent=2), encoding="utf-8")
    print(f"SITEWIDE total={len(routes)*len(WIDTHS)} "
          f"passed={len(report)} failed={len(failures)}", flush=True)
    if failures:
        raise AssertionError(f"{len(failures)} responsive/accessibility failures. "
                             "Inspect results.json and screenshots.")
    print("PASS ALL anonymous/protected-gate responsive route checks", flush=True)


if __name__ == "__main__":
    main()
