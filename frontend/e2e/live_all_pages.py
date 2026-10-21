"""Read-only, live Amaris frontend route and internal-link inventory.

Lists every checked-in Next app/page.tsx entry point, probes each anonymously,
includes safe dynamic fixtures, then inspects internal links found on public
pages. Protected content is classified AUTH_REQUIRED rather than claimed tested.
Never sends form submissions, credentials, payments or POST requests.
"""
from __future__ import annotations

import concurrent.futures
import html.parser
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
OUT = ROOT / "artifacts" / "live-site-pages"
OUT.mkdir(parents=True, exist_ok=True)
BASE = os.environ.get(
    "AMARIS_LIVE_BASE", "https://amaris-mathematics-academy-live-students.onrender.com"
).rstrip("/")
BACKEND = "https://amaris-production-web.onrender.com"
EXAMPLE_DYNAMIC = {
    "courses/[slug]": "/courses/caps-grade-12-mathematics",
    "checkout/[slug]": "/checkout/caps-grade-12-mathematics",
    "learn/[courseSlug]/[lessonSlug]": "/learn/caps-grade-12-mathematics/algebra-and-equations",
    "errors/[code]": "/errors/404",
}
AUTH_PREFIXES = (
    "/dashboard", "/checkout/", "/learn/", "/documents/invoice",
    "/tutor/dashboard", "/book-online-live-class/checkout",
    "/book-online-live-class/confirmation", "/request-a-video/confirmation",
)
CONTEXT_REQUIRED = (
    "/auth/", "/reset-password", "/verify-email", "/tutor/verify-email",
    "/request-a-video/invoice", "/payments/", "/session-expired",
)
SKIP_LINK_PREFIXES = (
    "/auth/", "/api/", "/checkout/", "/learn/", "/dashboard",
    "/documents/invoice", "/book-online-live-class/checkout",
    "/book-online-live-class/confirmation", "/request-a-video/invoice",
    "/request-a-video/video", "/tutor/dashboard", "/payments/",
)


class Links(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hrefs: set[str] = set()
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "a" and isinstance(values.get("href"), str):
            self.hrefs.add(values["href"])
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def request(url: str, accept: str = "text/html") -> dict:
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Amaris-live-read-only-page-audit/1.0", "Accept": accept}
            )
            with urllib.request.urlopen(req, timeout=35) as response:
                status = response.status
                final = response.url
                content_type = response.headers.get("Content-Type", "")
                body = response.read(500000).decode("utf-8", "replace")
            return {"status": status, "final": final, "contentType": content_type,
                    "body": body, "error": None}
        except urllib.error.HTTPError as err:
            last = {"status": err.code, "final": err.url, "contentType": "",
                    "body": "", "error": f"HTTP {err.code}"}
            if err.code not in (502, 503, 504, 429):
                return last
        except Exception as err:
            last = {"status": 0, "final": url, "contentType": "",
                    "body": "", "error": type(err).__name__}
        if attempt < 2:
            time.sleep(2 + attempt * 3)
    return last or {"status": 0, "final": url, "contentType": "",
                    "body": "", "error": "unknown network error"}


def classify(route: str) -> str:
    if route.startswith(AUTH_PREFIXES):
        return "AUTH_REQUIRED"
    if route.startswith(CONTEXT_REQUIRED) or route == "/documents/invoice":
        return "CONTEXT_REQUIRED"
    return "PUBLIC"


def pages() -> list[dict]:
    targets = []
    for f in sorted(APP.rglob("page.tsx")):
        rel = f.parent.relative_to(APP).as_posix()
        route = "/" if rel == "." else "/" + rel
        if "[" in route:
            if rel not in EXAMPLE_DYNAMIC:
                raise AssertionError(f"Unknown dynamic page needs a safe fixture: {route}")
            route = EXAMPLE_DYNAMIC[rel]
        targets.append({"route": route, "source": f.relative_to(ROOT).as_posix(),
                        "category": classify(route)})
    if len(targets) < 47:
        raise AssertionError(f"Missing page routes: only {len(targets)} found")
    return targets


def probe(target: dict) -> dict:
    url = BASE + target["route"]
    data = request(url)
    links = Links()
    if "text/html" in data["contentType"].lower():
        links.feed(data["body"])
    kind = target["category"]
    status = data["status"]
    html_ok = "text/html" in data["contentType"].lower()
    if kind == "PUBLIC":
        verdict = "PASS" if status == 200 and html_ok else "FAIL"
    else:
        # An anonymous response cannot prove that the signed-in page works.
        # 401/403/404/login redirects and safe 200 pages are recorded, not
        # misrepresented as a successful authenticated journey.
        verdict = "AUTH_REQUIRED" if status in (200, 401, 403, 404) else "FAIL"
    return {**target, "status": status, "verdict": verdict, "title": links.title[:150],
            "finalPath": urllib.parse.urlsplit(data["final"]).path,
            "contentType": data["contentType"], "error": data["error"],
            "links": sorted(links.hrefs), "bytes": len(data["body"])}


def inspect_links(rows: list[dict]):
    found = set()
    for row in rows:
        if row["verdict"] != "PASS":
            continue
        for raw in row["links"]:
            if not raw or raw.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
                continue
            target = urllib.parse.urljoin(BASE + row["route"], raw)
            u = urllib.parse.urlsplit(target)
            if u.netloc != urllib.parse.urlsplit(BASE).netloc:
                continue
            path = urllib.parse.unquote(u.path)
            if path.startswith(SKIP_LINK_PREFIXES):
                continue
            if path.startswith("/_next/") or path.startswith("/assets/"):
                continue
            if not path.startswith("/"):
                continue
            found.add(path)
    # URL paths only, no query strings containing email/address or auth tokens.
    audited = []
    for path in sorted(found)[:180]:
        result = request(BASE + urllib.parse.quote(path, safe="/-._~"))
        status = result["status"]
        verdict = "PASS" if status in (200, 301, 302, 307, 308) else "BROKEN"
        audited.append({"route": path, "status": status, "verdict": verdict,
                        "error": result["error"]})
    return audited, len(found)


def main():
    targets = pages()
    print(f"INVENTORY {len(targets)} Next.js page routes", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        rows = list(pool.map(probe, targets))
    for row in rows:
        print(f"{row['verdict']:14} HTTP {row['status']:3} {row['route']} [{row['category']}]", flush=True)
    checked, discovered = inspect_links(rows)
    for link in checked:
        if link["verdict"] == "BROKEN":
            print(f"BROKEN INTERNAL LINK HTTP {link['status']} {link['route']}", flush=True)
    api = []
    for origin, path in (
        (BASE, "/health/ready/"),
        (BASE, "/api/auth-state"),
        (BACKEND, "/health/"),
        (BACKEND, "/health/ready/"),
        (BACKEND, "/api/v1/announcements/"),
    ):
        a = request(origin + path, accept="application/json")
        is_json = "application/json" in a["contentType"].lower()
        api.append({"path": origin + path, "status": a["status"], "json": is_json, "error": a["error"]})
        print(f"BACKEND/FRONTEND PROBE {a['status']:3} {origin + path} json={is_json}", flush=True)
    bad_pages = [r for r in rows if r["verdict"] == "FAIL"]
    broken = [r for r in checked if r["verdict"] == "BROKEN"]
    bad_api = [r for r in api if r["status"] != 200 or not r["json"]]
    output = {
        "release": os.environ.get("GITHUB_SHA", "unknown"),
        "base": BASE, "pagesFound": len(targets),
        "publicPass": sum(r["verdict"] == "PASS" for r in rows),
        "authOrContextRequired": sum(r["verdict"] == "AUTH_REQUIRED" for r in rows),
        "publicFail": len(bad_pages), "internalLinksFound": discovered,
        "internalLinksTested": len(checked), "brokenInternalLinks": len(broken),
        "apiFailures": len(bad_api),
        "routes": [{k: v for k, v in r.items() if k != "links"} for r in rows],
        "links": checked, "api": api,
    }
    (OUT / "report.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    md = [
        "# Amaris live site — anonymous route and link audit",
        "",
        f"Page entrypoints: **{len(targets)}**; public PASS: **{output['publicPass']}**; "
        f"requires login/context: **{output['authOrContextRequired']}**; public FAIL: **{len(bad_pages)}**.",
        f"Internal links: **{len(checked)}/{discovered}** checked; broken: **{len(broken)}**.",
        f"Public frontend/backend endpoints failing: **{len(bad_api)}**.",
        "",
        "Protected/conditional pages were not logged into; this audit does NOT validate "
        "private dashboards, actual payments, invoice downloads or lesson playback.",
        "",
        "| Route | HTTP | Result |",
        "|---|---:|---|",
    ]
    for row in rows:
        md.append(f"| \`{row['route']}\` | {row['status']} | {row['verdict']} |")
    (OUT / "summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"LIVE SITE TOTAL pages={len(rows)} public_pass={output['publicPass']} "
          f"conditional={output['authOrContextRequired']} public_fail={len(bad_pages)} "
          f"links_tested={len(checked)} broken_links={len(broken)} api_failures={len(bad_api)}", flush=True)
    if bad_pages or broken or bad_api:
        raise AssertionError(f"Site audit FAILED: pages={len(bad_pages)}, links={len(broken)}, api={len(bad_api)}")
    print("PASS live public page, internal link and read-only API gate", flush=True)


if __name__ == "__main__":
    main()
