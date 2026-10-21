"""Audit every Next app/page.tsx entrypoint at representative device sizes.

This is an unauthenticated, production-equivalent local Chrome audit.
Protected student/tutor/payment routes are tested in their public/redirect state.
Dynamic routes use deliberately invalid example slugs and are reported as unverified.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from collections import Counter
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts" / "sitewide-responsive"
ART.mkdir(parents=True, exist_ok=True)
BASE = "http://127.0.0.1:3016"

DEVICES = (
    ("small-phone", 320, 700, True),
    ("iphone", 390, 844, True),
    ("android-landscape", 667, 375, True),
    ("tablet-portrait", 768, 1024, False),
    ("tablet-landscape", 1024, 768, False),
    ("laptop", 1440, 900, False),
    ("wide-desktop", 1920, 1080, False),
)

CONDITIONAL = (
    "/checkout/",
    "/learn/",
    "/errors/",
    "/book-online-live-class/checkout",
    "/book-online-live-class/confirmation",
    "/request-a-video/confirmation",
    "/documents/invoice",
    "/dashboard",
    "/tutor/dashboard",
)

INIT = r"""
(() => {
  window.__amarisResponsive = {cls:0, lcp:0};
  try {
    new PerformanceObserver(list => {
      for (const entry of list.getEntries()) {
        if (!entry.hadRecentInput) window.__amarisResponsive.cls += entry.value;
      }
    }).observe({type:'layout-shift', buffered:true});
  } catch {}
  try {
    new PerformanceObserver(list => {
      const entries=list.getEntries();
      if(entries.length) window.__amarisResponsive.lcp=entries[entries.length-1].startTime;
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
    viewport:w, documentWidth:root.scrollWidth,
    bodyWidth:document.body?.scrollWidth||0,
    cls:window.__amarisResponsive?.cls||0,
    lcp:window.__amarisResponsive?.lcp||0,
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
        result.append({"route": path, "source": str(f.relative_to(ROOT)),
                       "dynamic": dynamic,
                       "conditional": dynamic or any(path.startswith(x) for x in CONDITIONAL)})
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
    errors=[]
    page.on("pageerror",lambda error:errors.append(str(error)[:180]))
    res={"route":route["route"],"source":route["source"],
         "device":name,"width":width,"height":height,
         "dynamic":route["dynamic"],"conditional":route["conditional"],
         "status":"pending","errors":[]}
    try:
        response=page.goto(BASE+route["route"],wait_until="domcontentloaded",timeout=35000)
        res["http"]=response.status if response else None
        res["finalPath"]=page.url.replace(BASE,"")
        page.wait_for_timeout(350)
        before=page.evaluate(METRICS)
        # Scroll to expose lazy content and catch post-render shifting.
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(300)
        after=page.evaluate(METRICS)
        res["documentWidth"]=max(before["documentWidth"],after["documentWidth"])
        res["overflowPx"]=max(0,res["documentWidth"]-width)
        res["cls"]=round(max(before["cls"],after["cls"]),4)
        res["lcpMs"]=round(after["lcp"]) if after["lcp"] else None
        res["offenders"]=after["offenders"] if res["overflowPx"]>2 else []
        res["errors"]=errors[:3]
        if res["overflowPx"]>2:
            res["status"]="FAIL_OVERFLOW"
        elif res["cls"]>0.10:
            res["status"]="FAIL_CLS"
        elif res["http"] and res["http"]>=500:
            res["status"]="FAIL_HTTP_5XX"
        elif res["http"] and res["http"]>=400:
            res["status"]="CONDITIONAL_UNVERIFIED" if route["conditional"] else "FAIL_HTTP_4XX"
        else:
            res["status"]="PASS_CONDITIONAL" if route["conditional"] else "PASS"

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
        print(f'{res["status"]:>23} {name:20} {route["route"]:48} HTTP={res.get("http")} overflow={res.get("overflowPx")} CLS={res.get("cls")}',flush=True)
    except (PlaywrightError, Exception) as exc:
        res["status"]="ERROR"
        res["errors"]=[str(exc)[:360]]
        print(f'ERROR {name} {route["route"]}: {str(exc)[:240]}',flush=True)
    finally:
        context.close()
    return res


def run():
    routes=discover()
    if not routes or len(routes)<40:
        raise RuntimeError(f"Expected at least 40 discoverable route entries, found {len(routes)}")
    screenshots=[]
    results=[]
    with (ART/"nitro.log").open("w") as log:
        server=subprocess.Popen(["node",".output/server/index.mjs"],cwd=ROOT,
                                env={**os.environ,"HOST":"127.0.0.1","PORT":"3016",
                                     "NITRO_PORT":"3016","NODE_ENV":"production",
                                     "CMS_API_URL":""},stdout=log,stderr=subprocess.STDOUT)
        try:
            wait_for_server(server)
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=os.environ.get("AMARIS_CHROME_PATH") or None,
                                          headless=True,args=["--no-sandbox","--disable-dev-shm-usage"])
                for device in DEVICES:
                    for route in routes:
                        results.append(audit_page(browser,route,device,screenshots))
                browser.close()
        finally:
            server.terminate()
            try: server.wait(timeout=8)
            except subprocess.TimeoutExpired: server.kill()
    counts=Counter(row["status"] for row in results)
    failed=[row for row in results if row["status"].startswith("FAIL") or row["status"]=="ERROR"]
    conditional=[row for row in results if "CONDITIONAL" in row["status"]]
    summary={"routesDiscovered":len(routes),"viewports":len(DEVICES),"totalChecks":len(results),
             "counts":dict(counts),"failures":failed,"conditionalChecks":len(conditional),
             "screenshots":screenshots,"caveats":[
                 "Automated responsive layout on Chromium; not every physical device or browser.",
                 "Unauthenticated pages only; dashboards/payments/bookings need synthetic signed-in journey tests.",
                 "Dynamic routes use invalid test slugs and may return expected 404.",
                 "Locally served production-equivalent Nitro build, not live Render or real-user telemetry.",
             ]}
    (ART/"results.json").write_text(json.dumps({"summary":summary,"results":results},indent=2))
    with (ART/"summary.md").open("w") as f:
        f.write("# Amaris sitewide responsive audit\n\n")
        f.write(f'Routes: **{len(routes)}**; device sizes: **{len(DEVICES)}**; checks: **{len(results)}**.\n\n')
        f.write("## Status counts\n\n")
        for status,count in counts.most_common(): f.write(f"- {status}: {count}\n")
        f.write("\n## Failure details\n\n")
        for x in failed[:100]: f.write(f'- {x["route"]} at {x["width"]}px: {x["status"]}; overflow {x.get("overflowPx","?")}px; HTTP {x.get("http","?")}; elements {x.get("offenders",[])[:2]}; {x.get("errors",[])[:1]}\n')
        f.write("\n## Coverage restrictions\n\n"+"\n".join(f"- {x}" for x in summary["caveats"]))
    print("AUDIT SUMMARY",json.dumps({k:v for k,v in summary.items() if k not in ("failures","screenshots")}),flush=True)
    if failed:
        raise RuntimeError(f"RESPONSIVE AUDIT FAILED: {len(failed)} failing device/route combinations")
    print("PASS sitewide anonymous responsive audit",flush=True)


if __name__=="__main__":
    run()
