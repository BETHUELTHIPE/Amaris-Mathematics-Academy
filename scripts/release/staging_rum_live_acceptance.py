"""Staging-only anonymous RUM HTTP and Chrome acceptance.

Never uses production URLs, login credentials, cookies or payment endpoints.
Synthetic samples are marked under the 'other-public' route category.
"""
import json
import os
import time
import urllib.error
import urllib.request
from playwright.sync_api import sync_playwright

FRONT = "https://amaris-mathematics-academy-staging-x4ax.onrender.com"
BACK = "https://amaris-mathematics-academy-staging.onrender.com"

def get(url):
    for attempt in range(6):
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers={"User-Agent": "Amaris-Staging-RUM-Acceptance"}),
                timeout=35,
            ) as response:
                if response.status == 200:
                    print("PASS staging public HTTP 200", url.split(".onrender.com")[-1], flush=True)
                    return
        except Exception as exc:
            if attempt == 5:
                raise RuntimeError(f"Staging public health unavailable: {type(exc).__name__}") from exc
        time.sleep(6)
    raise RuntimeError("Staging health check failed")

def post(payload, origin):
    data = json.dumps(payload, separators=(",", ":")).encode()
    req = urllib.request.Request(
        FRONT + "/api/field-vitals",
        data=data, method="POST",
        headers={
            "Content-Type": "application/json",
            "Origin": origin,
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Amaris-Staging-RUM-Acceptance",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=32) as res:
            return res.status
    except urllib.error.HTTPError as err:
        return err.code

def synthetic_validation():
    example = {"name": "LCP", "value": 2150, "route": "other-public",
               "device": "mobile", "network": "unknown"}
    if post({"records": [example]}, "https://not-your-staging.example") != 403:
        raise RuntimeError("Cross-origin RUM attempt not denied")
    print("PASS same-origin protection 403", flush=True)
    malformed_status = post({"records": [{**example, "account_id": "forbidden"}]}, FRONT)
    if malformed_status != 400:
        if malformed_status == 403:
            raise RuntimeError(
                "The staging RUM forwarder rejected its real public Origin. "
                "Verify the staging frontend RUM_ALLOWED_ORIGIN points to its "
                "exact HTTPS public Render hostname; never trust Host or forwarded headers."
            )
        raise RuntimeError(f"Non-allowlisted identifying field not rejected: HTTP {malformed_status}")
    print("PASS private-field rejection 400", flush=True)
    for batch in range(7):
        metrics = [{**example, "value": 2100 + batch * 25} for _ in range(3)]
        status = post({"records": metrics}, FRONT)
        if status != 204:
            raise RuntimeError(f"Staging browser forwarder did not complete Django write: HTTP {status}, batch {batch+1}")
    print("PASS 21 synthetic coarse LCP samples via staging Next->Django->Supabase", flush=True)

def browser_validation():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=os.getenv("AMARIS_CHROME_PATH") or None,
            headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        # Enroll this single disposable test browser in the sampling cohort.
        # Observe *actual fetch responses*, without replacing recorded metric
        # values or creating an artificial Web Vital event.
        ctx.add_init_script("""
            Math.random = () => 0;
            window.__amarisRumHttpStatuses = [];
            const originalFetch = window.fetch.bind(window);
            window.fetch = (...args) => {
              const url = typeof args[0] === "string" ? args[0] : args[0]?.url;
              const result = originalFetch(...args);
              if (url && url.includes("/api/field-vitals")) {
                result.then(r => window.__amarisRumHttpStatuses.push(r.status),
                            () => window.__amarisRumHttpStatuses.push(0));
              }
              return result;
            };
        """)
        requests = []
        ctx.on("request", lambda req: requests.append(req.post_data_json)
               if "/api/field-vitals" in req.url and req.method == "POST" else None)
        page = ctx.new_page()
        try:
            page.goto(FRONT + "/", wait_until="domcontentloaded", timeout=80000)
            page.locator("h1").first.wait_for(timeout=30000)
            page.wait_for_timeout(2500)
            diagnostics = page.evaluate("""() => ({
                dnt: navigator.doNotTrack === "1",
                gpc: navigator.globalPrivacyControl === true,
                hidden: document.visibilityState === "hidden",
                pageReady: document.readyState,
                hasPerformanceObserver: "PerformanceObserver" in window,
            })""")
            print("Browser telemetry eligibility:", json.dumps(diagnostics, sort_keys=True), flush=True)
            if diagnostics["dnt"] or diagnostics["gpc"]:
                raise RuntimeError("Test Chrome has a privacy opt-out enabled; do not override it")
            # Finalize the browser's *observed* metrics by simulating the
            # page-hidden lifecycle, without creating fake Web Vital values.
            page.evaluate("""() => {
                Object.defineProperty(document, "visibilityState", {
                    configurable: true, get: () => "hidden"
                });
                Object.defineProperty(document, "hidden", {
                    configurable: true, get: () => true
                });
                document.dispatchEvent(new Event("visibilitychange"));
                setTimeout(() => window.dispatchEvent(new Event("pagehide")), 350);
            }""")
            try:
                page.wait_for_function(
                    "() => window.__amarisRumHttpStatuses.length > 0",
                    timeout=22000,
                )
            except Exception as exc:
                raise RuntimeError(
                    "Real Chrome did not emit a Web Vitals fetch. Verify the "
                    "staging frontend was rebuilt with NEXT_PUBLIC_ENABLE_WEB_VITALS=true "
                    "and the browser sample is enabled."
                ) from exc
            statuses = page.evaluate("window.__amarisRumHttpStatuses")
            if not statuses or any(value != 204 for value in statuses):
                raise RuntimeError(f"Real Chrome RUM forwarder returned non-204 status(es): {statuses}")
            if not requests:
                raise RuntimeError("No genuine Chrome POST request was observed")
            for data in requests:
                if not isinstance(data, dict) or set(data) != {"records"}:
                    raise RuntimeError("Browser payload included unexpected fields")
                if any(
                    not isinstance(record, dict)
                    or set(record) != {"name", "value", "route", "device", "network"}
                    or record["name"] not in ("LCP", "INP", "CLS")
                    or record["route"] != "home"
                    for record in data["records"]
                ):
                    raise RuntimeError("Browser payload included identifying or invalid fields")
            print("PASS real mobile Chrome -> staging Next -> Django: HTTP 204, privacy-safe browser metrics", flush=True)
        finally:
            ctx.close()
            browser.close()

def main():
    get(BACK + "/health/")
    get(FRONT + "/")
    synthetic_validation()
    browser_validation()
    print("PASS staging telemetry end-to-end acceptance", flush=True)

if __name__ == "__main__":
    main()
