"""Read-only checks of every published course detail subpage.

Django's public course API and bundled fallback course slug data are both
considered. No student enrolment/checkout endpoints are called.
"""
from __future__ import annotations

import concurrent.futures
import json
import re
from pathlib import Path
from urllib.parse import urljoin

from live_all_pages import APP, BACKEND, BASE, OUT, ROOT, request


def published_slugs():
    source = (ROOT / "lib" / "courses.ts").read_text(encoding="utf-8")
    local = set(re.findall(r'slug:\\s*["\\\']([a-z0-9-]+)["\\\']', source))
    live = set()
    endpoint = BACKEND + "/api/v1/courses/?page_size=100"
    api_calls = 0
    while endpoint and api_calls < 6:
        response = request(endpoint)
        if response["status"] != 200:
            raise AssertionError(f"Published course API returned {response['status']} on page {api_calls+1}")
        try:
            payload = json.loads(response["body"])
        except ValueError:
            raise AssertionError("Published courses endpoint did not return JSON") from None
        values = payload.get("results", []) if isinstance(payload, dict) else payload
        if not isinstance(values, list):
            raise AssertionError("Unexpected published course catalogue response")
        for item in values:
            if isinstance(item, dict):
                slug = item.get("slug")
                if isinstance(slug, str) and re.fullmatch(r"[a-z0-9-]{1,120}", slug):
                    live.add(slug)
        next_url = payload.get("next") if isinstance(payload, dict) else None
        endpoint = urljoin(BACKEND, next_url) if isinstance(next_url, str) and next_url else None
        if endpoint and not endpoint.startswith(BACKEND + "/api/v1/courses/"):
            raise AssertionError("Untrusted published course pagination URL")
        api_calls += 1
    if endpoint:
        raise AssertionError("Published courses exceed pagination safety limit")
    slugs = sorted(local | live)
    if not slugs:
        raise AssertionError("No source-backed published or fallback course slug found")
    if len(slugs) > 300:
        raise AssertionError("Too many course detail pages; limit is 300")
    return slugs, sorted(live), sorted(local)


def main():
    slugs, live, local = published_slugs()
    print(f"COURSE SUBPAGES published={len(live)} static_fallback={len(local)} distinct={len(slugs)}", flush=True)
    def check(slug):
        path = "/courses/" + slug
        r = request(BASE + path)
        return {"path": path, "status": r["status"],
                "contentType": r["contentType"],
                "pass": r["status"] == 200 and "text/html" in r["contentType"]}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(check, slugs))
    failed = []
    for row in results:
        print(("PASS" if row["pass"] else "FAIL") + f" HTTP {row['status']} {row['path']}", flush=True)
        if not row["pass"]:
            failed.append(row)
    out = {"publishedCMS":len(live),"fallback":len(local),"tested":len(results),
           "passed":len(results)-len(failed),"failed":len(failed),"routes":results}
    (OUT / "course-detail-subpages.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"COURSE DETAIL TOTAL {len(results)} passed={out['passed']} failed={len(failed)}", flush=True)
    if failed:
        raise AssertionError(f"{len(failed)} course detail subpages failed")
    print("PASS every public course detail subpage", flush=True)


if __name__ == "__main__":
    main()
