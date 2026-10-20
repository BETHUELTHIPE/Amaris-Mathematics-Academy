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
        ctx.add_init_script("Math.random = () => 0")
        page = ctx.new_page()
        page.goto(FRONT + "/", wait_until="domcontentloaded", timeout=80000)
        page.locator("h1").first.wait_for(timeout=30000)
        page.wait_for_timeout(2500)
        try:
            with page.expect_response(
                lambda response: "/api/field-vitals" in response.url and response.request.method == "POST",
                timeout=22000,
            ) as response_info:
                page.evaluate("window.dispatchEvent(new Event('pagehide'))")
            response = response_info.value
            if response.status != 204:
                raise RuntimeError(f"Real Chrome Web Vital request returned HTTP {response.status}")
            print("PASS real mobile Chrome -> staging Next -> Django: HTTP 204", flush=True)
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
