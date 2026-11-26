"""Audit every Next app/page.tsx entrypoint at representative device sizes.

This is an unauthenticated, production-equivalent local Chrome audit.
Protected student/tutor/payment routes are tested in their public/redirect state.
Real course/recovery details use known-good fixtures; invalid slugs are negative tests, never proof of working pages.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts" / "sitewide-responsive"
ART.mkdir(parents=True, exist_ok=True)
LIVE_ORIGIN = os.environ.get("AMARIS_SITEWIDE_ORIGIN", "").rstrip("/")
BASE = LIVE_ORIGIN or "http://127.0.0.1:3016"
LCP_BUDGET_MS = 2500

DEVICES = (
    ("small-phone", 320, 700, True),
    ("iphone", 390, 844, True),
    ("android-landscape", 667, 375, True),
    ("tablet-portrait", 768, 1024, False),
    ("tablet-landscape", 1024, 768, False),
    ("laptop", 1440, 900, False),
    ("wide-desktop", 1920, 1080, False),
)

PROTECTED_PREFIXES = (
    "/account/complete-profile",
    "/book-online-class",
    "/book-online-live-class",
    "/checkout",
    "/dashboard",
    "/documents",
    "/learn",
    "/request-a-video",
    "/reset-password",
    "/tutor/dashboard",
)
PUBLIC_EXCEPTIONS = {"/reset-password/verify"}
# Source-backed public fixtures with known-good local fallbacks.
DYNAMIC_PUBLIC_FIXTURES = {
    "courses/[slug]": {
        "route": "/courses/caps-grade-12-mathematics",
        "heading": "CAPS Grade 12 Mathematics",
        "bodyText": "Course structure",
        "sourceFixture": ROOT / "lib" / "courses.ts",
        "sourceNeedle": 'slug: "caps-grade-12-mathematics"',
    },
    "errors/[code]": {
        "route": "/errors/404",
        "heading": "That page is not on the syllabus.",
        "bodyText": "Browse mathematics courses",
        "sourceFixture": ROOT / "lib" / "recovery.ts",
        "sourceNeedle": '"404": {',
    },
}

INIT = r"""
(() => {
  window.__amarisResponsive = {cls:0, lcp:0, lcpElement:null};
  let sessionStart = 0, previousShift = 0, sessionValue = 0;
  try {
    new PerformanceObserver(list => {
      for (const entry of list.getEntries()) {
        if (entry.hadRecentInput) continue;
        if (sessionValue && entry.startTime - previousShift < 1000 &&
            entry.startTime - sessionStart < 5000) {
          sessionValue += entry.value;
        } else {
          sessionStart = entry.startTime;
          sessionValue = entry.value;
        }
        previousShift = entry.startTime;
        window.__amarisResponsive.cls = Math.max(window.__amarisResponsive.cls, sessionValue);
      }
    }).observe({type:'layout-shift', buffered:true});
  } catch {}
  try {
    new PerformanceObserver(list => {
      const entries=list.getEntries();
      const candidate = entries.at(-1);
      if (candidate) {
        window.__amarisResponsive.lcp = candidate.startTime;
        window.__amarisResponsive.lcpElement = candidate.element?.tagName ?? null;
      }
    }).observe({type:'largest-contentful-paint', buffered:true});
  } catch {}
})();
"""

METRICS = r"""() => {
  const w=window.innerWidth;
  const root=document.documentElement;
  const offenders=Array.from(document.querySelectorAll('body *'))
    .map(el => ({el, rect:el.getBoundingClientRect()}))
    .filter(x => x.rect.width>0 && (x.rect.right>w+3 || x.rect.left < -3))
    .slice(0,5).map(x => ({
      tag:x.el.tagName.toLowerCase(),
      className:String(x.el.className || '').slice(0,90),
      right:Math.round(x.rect.right), left:Math.round(x.rect.left)
    }));
  return {
    viewport:w, documentWidth:Math.max(root.scrollWidth, document.body?.scrollWidth || 0),
    hasLayout: Boolean(getComputedStyle(root).getPropertyValue('--background').trim()),
    hasHeading: Boolean(document.querySelector('h1')?.textContent?.trim()),
    bodyWidth:document.body?.scrollWidth||0,
    cls:window.__amarisResponsive?.cls||0,
    lcp:window.__amarisResponsive?.lcp||0,
    lcpElement:window.__amarisResponsive?.lcpElement,
    ttfb:performance.getEntriesByType('navigation')[0]?.responseStart ?? null,
    resources:performance.getEntriesByType('resource')
      .filter(entry => new URL(entry.name).origin === location.origin)
      .reduce((bytes, entry) => bytes + entry.transferSize, 0),
    offenders
  };
}"""


def discover():
    pages = sorted((ROOT / "app").rglob("page.tsx"))
    result = []
    for f in pages:
        rel = f.parent.relative_to(ROOT / "app")
        parts = [] if str(rel) == "." else list(rel.parts)
        dynamic = any("[" in part for part in parts)
        path = "/" + "/".join(re.sub(r"\[.*?\]", "responsive-test-invalid-slug", p) for p in parts)
        key = "/".join(parts)
        fixture = DYNAMIC_PUBLIC_FIXTURES.get(key)
        protected = path not in PUBLIC_EXCEPTIONS and any(
            path == prefix or path.startswith(prefix + "/") for prefix in PROTECTED_PREFIXES
        )
        result.append({
            "route": path, "source": str(f.relative_to(ROOT)),
            "dynamic": dynamic,
            "coverage": "negative-404" if fixture else ("protected" if dynamic or protected else "public"),
            "conditional": (dynamic or protected) and not bool(fixture),
        })
        if fixture:
            if fixture["sourceNeedle"] not in fixture["sourceFixture"].read_text(encoding="utf-8"):
                raise RuntimeError(f"Stale positive fixture for {key}")
            result.append({
                "route": fixture["route"],
                "source": str(f.relative_to(ROOT)),
                "dynamic": True,
                "coverage": "valid-dynamic", "conditional": False,
                "expectedHeading": fixture["heading"],
                "expectedBodyText": fixture["bodyText"],
            })
    return result


def wait_for_server(proc):
    for _ in range(80):
        if proc.poll() is not None:
            raise RuntimeError(f"Nitro exited during startup: {proc.returncode}")
        try:
            with urlopen(BASE + "/", timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(1)
    raise RuntimeError("Nitro did not start")


def audit_page(browser, route, device, screenshots):
    name,width,height,mobile = device
    context=browser.new_context(viewport={"width":width,"height":height},
                                is_mobile=mobile,has_touch=mobile,
                                device_scale_factor=1,reduced_motion="reduce",
                                ignore_https_errors=False)
    context.add_init_script(INIT)
    page=context.new_page()
    throttled = bool(LIVE_ORIGIN) and width == 390
    if throttled:
        session = context.new_cdp_session(page)
        session.send("Network.enable")
        session.send("Network.emulateNetworkConditions", {
            "offline": False,
            "latency": 80,
            "downloadThroughput": 1_600_000 / 8,
            "uploadThroughput": 750_000 / 8,
        })
        session.send("Emulation.setCPUThrottlingRate", {"rate": 4})
    errors=[]
    page.on("pageerror",lambda error:errors.append(str(error)[:180]))
    res={"route":route["route"],"source":route["source"],
         "device":name,"width":width,"height":height,
         "dynamic":route["dynamic"],"conditional":route["conditional"],
         "coverage":route["coverage"],"status":"pending","errors":[]}
    try:
        response=page.goto(BASE+route["route"],wait_until="domcontentloaded",timeout=35000)
        res["http"]=response.status if response else None
        res["finalPath"]=page.url.replace(BASE,"")
        if not res["http"] or res["http"] < 500:
            try:
                page.wait_for_load_state("load", timeout=6_000)
            except PlaywrightTimeoutError:
                # Optional media can continue loading after the main content paints.
                res["loadEventObserved"] = False
            else:
                res["loadEventObserved"] = True
        page.wait_for_timeout(350)
        before=page.evaluate(METRICS)
        # Scroll to expose lazy content and catch post-render shifting.
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(300)
        after=page.evaluate(METRICS)
        res["documentWidth"]=max(before["documentWidth"],after["documentWidth"])
        res["overflowPx"]=max(0,res["documentWidth"]-width)
        res["cls"]=round(max(before["cls"],after["cls"]),4)
        res["lcpMs"]=round(before["lcp"]) if before["lcp"] else None
        res["lcpElement"]=before["lcpElement"]
        res["ttfbMs"]=round(before["ttfb"]) if before["ttfb"] is not None else None
        res["resourceTransferBytes"]=before["resources"]
        res["throttled"]=throttled
        res["offenders"]=after["offenders"] if res["overflowPx"]>2 else []
        res["errors"]=errors[:3]
        coverage = route["coverage"]
        if coverage == "valid-dynamic":
            # A generic 200, login redirect or branded 404 cannot pass this.
            heading = page.locator("h1").first.inner_text(timeout=5000).strip() if page.locator("h1").count() else ""
            res["heading"] = heading[:180]
            res["positiveContentMatched"] = (
                heading == route["expectedHeading"] and
                page.get_by_text(route["expectedBodyText"], exact=False).count() > 0
            )
        if res["http"] and res["http"] >= 500:
            res["status"] = "FAIL_HTTP_5XX"
        elif coverage != "negative-404" and (not after["hasLayout"] or not after["hasHeading"]):
            res["status"] = "FAIL_PAGE_RENDER"
        elif coverage == "valid-dynamic":
            if (res["http"] != 200 or res["finalPath"] != route["route"]
                    or not res["positiveContentMatched"]):
                res["status"] = "FAIL_VALID_DYNAMIC_PAGE"
            elif res["overflowPx"] > 2:
                res["status"] = "FAIL_OVERFLOW"
            elif res["cls"] > 0.10:
                res["status"] = "FAIL_CLS"
            else:
                res["status"] = "PASS_VALID_DYNAMIC"
        elif coverage == "negative-404":
            # Expected 404 is not a real page-rendering success.
            res["status"] = (
                "PASS_EXPECTED_404" if res["http"] == 404 and res["finalPath"] == route["route"]
                else "FAIL_NEGATIVE_EXPECTED_404"
            )
        elif res["overflowPx"] > 2:
            res["status"] = "FAIL_OVERFLOW"
        elif res["cls"] > 0.10:
            res["status"] = "FAIL_CLS"
        elif res["http"] and res["http"] >= 400:
            res["status"] = "CONDITIONAL_UNVERIFIED" if route["conditional"] else "FAIL_HTTP_4XX"
        else:
            res["status"] = "PASS_CONDITIONAL" if route["conditional"] else "PASS"

        # Keep a visual evidence sample, plus capped failure screenshots.
        capture=(width==390 and route["route"] in {
            "/","/courses","/register","/book-online-live-class","/dashboard",
            "/tutor/dashboard","/support-our-project","/matric-upgrades"
        }) or (res["status"].startswith("FAIL") and len(screenshots)<25)
        if capture and len(screenshots)<38:
            filename=(route["route"].strip("/").replace("/","_") or "home")
            file=ART / f"{name}-{filename}.png"
            page.screenshot(path=str(file),full_page=True,animations="disabled",timeout=10000)
            screenshots.append(str(file.relative_to(ART)))
        print(f'{res["status"]:>23} {name:20} {route["route"]:48} HTTP={res.get("http")} overflow={res.get("overflowPx")} CLS={res.get("cls")} LCP={res.get("lcpMs")}ms TTFB={res.get("ttfbMs")}ms',flush=True)
    except Exception as exc:
        res["status"]="ERROR"
        res["errors"]=[str(exc)[:360]]
        print(f'ERROR {name} {route["route"]}: {str(exc)[:240]}',flush=True)
    finally:
        context.close()
    return res


@contextmanager
def serve_frontend():
    if LIVE_ORIGIN:
        yield
        return
    with (ART/"nitro.log").open("w") as log:
        server = subprocess.Popen(["node", ".output/server/index.mjs"], cwd=ROOT,
                                  env={**os.environ, "HOST": "127.0.0.1", "PORT": "3016",
                                       "NITRO_PORT": "3016", "NODE_ENV": "production",
                                       "CMS_API_URL": ""}, stdout=log, stderr=subprocess.STDOUT)
        try:
            wait_for_server(server)
            yield
        finally:
            server.terminate()
            try:
                server.wait(timeout=8)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


def run():
    routes=discover()
    if not routes or len(routes)<40:
        raise RuntimeError(f"Expected at least 40 discoverable route entries, found {len(routes)}")
    fixtures=[r for r in routes if r["coverage"] == "valid-dynamic"]
    if len(fixtures) != len(DYNAMIC_PUBLIC_FIXTURES):
        raise RuntimeError("Some known public dynamic pages lack a valid fixture.")
    screenshots=[]
    results=[]
    widths = os.environ.get("AMARIS_SITEWIDE_WIDTHS", "")
    requested_widths = {int(width) for width in widths.split(",")} if widths else set()
    devices = [device for device in DEVICES if not requested_widths or device[1] in requested_widths]
    if not devices or (requested_widths and {device[1] for device in devices} != requested_widths):
        raise ValueError("AMARIS_SITEWIDE_WIDTHS must use supported viewport widths")
    with serve_frontend(), sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get("AMARIS_CHROME_PATH") or None,
                                    headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            for device in devices:
                for route in routes:
                    results.append(audit_page(browser, route, device, screenshots))
        finally:
            browser.close()
    counts=Counter(row["status"] for row in results)
    failed=[row for row in results if row["status"].startswith("FAIL") or row["status"]=="ERROR"]
    conditional=[row for row in results if "CONDITIONAL" in row["status"]]
    valid_dynamic=[row for row in results if row["status"] == "PASS_VALID_DYNAMIC"]
    negative_404=[row for row in results if row["status"] == "PASS_EXPECTED_404"]
    verified_layout=[row for row in results if row["status"] in ("PASS", "PASS_VALID_DYNAMIC")]
    required_positive=len(fixtures) * len(devices)
    if len(valid_dynamic) != required_positive:
        failed.append({"status":"FAIL_POSITIVE_DYNAMIC_COVERAGE",
                       "required":required_positive,"actual":len(valid_dynamic)})
    phone = [row for row in verified_layout if row["throttled"]]
    slow_pages = sorted((row for row in phone if not row["lcpMs"] or row["lcpMs"] > LCP_BUDGET_MS),
                        key=lambda row: row["lcpMs"] or 0, reverse=True)
    if LIVE_ORIGIN and slow_pages:
        failed.extend({**row, "status": "FAIL_LAB_LCP"} for row in slow_pages)
    summary={"origin":BASE,"mobileLcpBudgetMs":LCP_BUDGET_MS,
             "mobileLcpPassing":len(phone) - len(slow_pages),"mobileLcpMeasured":len(phone),
             "pageTemplates":len({row["source"] for row in routes}),"routeCases":len(routes),"viewports":len(devices),"totalChecks":len(results),
             "counts":dict(counts),"failures":failed,"conditionalChecks":len(conditional),
             "validDynamicChecks":len(valid_dynamic),"validDynamicRoutes":len(fixtures),
             "negative404Checks":len(negative_404),"verifiedPageLayoutChecks":len(verified_layout),
             "screenshots":screenshots,"caveats":[
                 "Automated responsive layout on Chromium; not every physical device or browser.",
                 "Unauthenticated pages only; dashboards/payments/bookings need synthetic signed-in journey tests.",
                 "Invalid dynamic slugs are negative HTTP 404 checks, NOT proof of a real page.",
                 "Real course and error-detail paths require HTTP 200, the expected h1 and page content.",
                 "Authenticated lesson/checkout details remain unverified without isolated logged-in fixtures.",
                 "Live Chromium lab results, not real-user telemetry." if LIVE_ORIGIN else
                 "Locally served production-equivalent Nitro build.",
             ]}
    (ART/"results.json").write_text(json.dumps({"summary":summary,"results":results},indent=2))
    with (ART/"summary.md").open("w") as f:
        f.write("# Amaris sitewide responsive audit\n\n")
        f.write(f'Page templates: **{len({row["source"] for row in routes})}**; route cases: **{len(routes)}**; device sizes: **{len(devices)}**; checks: **{len(results)}**.\n\n')
        f.write("## Status counts\n\n")
        for status,count in counts.most_common(): f.write(f"- {status}: {count}\n")
        f.write("\n## Failure details\n\n")
        for x in failed[:100]: f.write(f'- {x.get("route","<coverage gate>")} at {x.get("width","?")}px: {x["status"]}; overflow {x.get("overflowPx","?")}px; HTTP {x.get("http","?")}; LCP {x.get("lcpMs","?")}ms; elements {x.get("offenders",[])[:2]}; {x.get("errors",[])[:1]}\n')
        f.write(f"\n## Verified page layout checks: {len(verified_layout)}\n")
        f.write(f"Valid dynamic page checks (HTTP 200 + content): **{len(valid_dynamic)}**.\n")
        f.write(f"Invalid dynamic 404 checks (excluded): **{len(negative_404)}**.\n")
        f.write("\n## Coverage restrictions\n\n"+"\n".join(f"- {x}" for x in summary["caveats"]))
    print("AUDIT SUMMARY",json.dumps({k:v for k,v in summary.items() if k not in ("failures","screenshots")}),flush=True)
    if failed:
        raise RuntimeError(f"RESPONSIVE AUDIT FAILED: {len(failed)} failing device/route combinations")
    print("PASS sitewide anonymous responsive audit",flush=True)


if __name__=="__main__":
    run()
