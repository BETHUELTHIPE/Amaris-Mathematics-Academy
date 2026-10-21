"""Supplemental Safari/WebKit and Firefox layout audit for all app page routes."""
import json
import os
from collections import Counter

from playwright.sync_api import sync_playwright

from sitewide_responsive_audit import ART, audit_page, discover, wait_for_server, ROOT, BASE
import subprocess


def main():
    engine = os.environ.get("AMARIS_BROWSER_ENGINE")
    if engine not in {"webkit", "firefox"}:
        raise RuntimeError("AMARIS_BROWSER_ENGINE must be webkit or firefox")
    routes = discover()
    devices = (
        (("safari-iphone", 390, 844, True), ("safari-ipad", 768, 1024, False))
        if engine == "webkit" else
        (("firefox-small", 390, 844, False), ("firefox-desktop", 1366, 768, False))
    )
    results, screenshots = [], []
    with (ART / f"{engine}-nitro.log").open("w") as log:
        server = subprocess.Popen(
            ["node", ".output/server/index.mjs"], cwd=ROOT,
            env={**os.environ, "HOST": "127.0.0.1", "PORT": "3016",
                 "NITRO_PORT": "3016", "NODE_ENV": "production", "CMS_API_URL": ""},
            stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            wait_for_server(server)
            with sync_playwright() as playwright:
                browser = getattr(playwright, engine).launch(
                    headless=True,
                    args=["--no-sandbox"] if engine == "firefox" else [],
                )
                for device in devices:
                    for route in routes:
                        results.append(audit_page(browser,route,device,screenshots))
                browser.close()
        finally:
            server.terminate()
            try: server.wait(timeout=8)
            except subprocess.TimeoutExpired: server.kill()
    counts=Counter(x["status"] for x in results)
    failures=[x for x in results if x["status"].startswith("FAIL") or x["status"]=="ERROR"]
    summary={"engine":engine,"routes":len(routes),"widths":[x[1] for x in devices],
             "checks":len(results),"statusCounts":dict(counts),"failures":failures}
    (ART / f"{engine}-results.json").write_text(json.dumps({"summary":summary,"results":results},indent=2))
    print("CROSS BROWSER SUMMARY",json.dumps(summary)[:9000],flush=True)
    if failures:
        raise RuntimeError(f"{engine} responsive failures {len(failures)}")
    print(f"PASS {engine} all anonymous responsive routes",flush=True)


if __name__ == "__main__":
    main()
