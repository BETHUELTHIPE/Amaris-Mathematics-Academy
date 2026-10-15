"""Deploy this approved finance candidate only to existing staging services.

Run inside the protected deployment job. Preserve secrets in the runner and
Render; do not print environment values. No infrastructure creation or payouts.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request

from verify_render_finance_preflight import NoRedirect
from verify_render_finance_preflight import main as preflight

REPO = "BETHUELTHIPE/Amaris-Mathematics-Academy"
BACKEND = "srv-dam2iivcgkoc7383tq50"
FRONTEND = "srv-daqf69qd0e5s73ac62n0"
FRONTEND_SHA = "776c8b18040b1c7af9194bb7468f94bfffea6f77"
ACTIVE = {
    "created",
    "build_in_progress",
    "pre_deploy_in_progress",
    "update_in_progress",
    "queued",
}


def request(url, key, method="GET", data=None):
    headers = {"Authorization": "Bearer " + key, "Accept": "application/json"}
    raw = None
    if data is not None:
        raw = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=raw, headers=headers, method=method)
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=30) as response:
        return json.load(response)


def render(path, method="GET", data=None):
    return request(
        "https://api.render.com/v1/" + path, os.environ["RENDER_API_KEY"], method, data
    )


def wait_checks(sha, required):
    for _ in range(40):
        data = request(
            f"https://api.github.com/repos/{REPO}/commits/{sha}/check-runs?per_page=100&filter=latest",
            os.environ["GITHUB_TOKEN"],
        )
        checks = [
            c
            for c in data["check_runs"]
            if c["name"] != "Verify actual staging isolation and finance prerequisites"
        ]
        for check in checks:
            if check["status"] == "completed" and check["conclusion"] not in (
                "success",
                "neutral",
                "skipped",
            ):
                raise RuntimeError("Candidate has a failed or cancelled release check")
        names = {c["name"] for c in checks}
        if required <= names and all(c["status"] == "completed" for c in checks):
            print("PASS exact candidate release checks:", sha, flush=True)
            return
        time.sleep(15)
    raise RuntimeError(
        "Candidate release checks did not finish within the deployment window"
    )


def deploy(service, sha):
    assert service in (BACKEND, FRONTEND)
    rows = render(f"services/{service}/deploys?limit=5")
    items = [r.get("deploy", r) for r in rows]
    existing = next(
        (
            d
            for d in items
            if d.get("commit", {}).get("id") == sha and d["status"] in ACTIVE | {"live"}
        ),
        None,
    )
    if existing:
        candidate = existing
    else:
        if any(d["status"] in ACTIVE for d in items):
            raise RuntimeError(
                "Another staging deployment is active; refusing concurrent release"
            )
        candidate = render(f"services/{service}/deploys", "POST", {"commitId": sha})
    deploy_id = candidate["id"]
    print("Staging deployment:", service, deploy_id, sha, flush=True)
    for _ in range(60):
        result = render(f"services/{service}/deploys/{deploy_id}")
        if result.get("commit", {}).get("id") != sha:
            raise RuntimeError("Render deployment selected a different revision")
        if result["status"] == "live":
            print("PASS live staging revision:", service, sha, flush=True)
            return
        if result["status"] not in ACTIVE:
            raise RuntimeError(
                "Staging deployment failed; production remains untouched"
            )
        time.sleep(15)
    raise RuntimeError("Staging deployment timed out; production remains untouched")


def main():
    if preflight():
        return 1
    sha = os.environ.get("CANDIDATE_SHA", "")
    if not re.fullmatch("[a-f0-9]{40}", sha):
        raise RuntimeError("An exact candidate SHA is required")
    wait_checks(
        sha,
        {
            "Python quality and Django checks",
            "PayFast sandbox and idempotency tests",
            "Repository secret scan",
            "Dependency vulnerability gates",
            "render-node",
        },
    )
    wait_checks(
        FRONTEND_SHA,
        {"Frontend lint, TypeScript and assistant tests", "applicant-journey"},
    )
    deploy(BACKEND, sha)
    deploy(FRONTEND, FRONTEND_SHA)
    # Django uses an APPEND_SLASH health URL; the Next.js frontend route is
    # canonical without a trailing slash. NoRedirect deliberately rejects 308s.
    health_routes = (
        ("https://amaris-mathematics-academy-staging.onrender.com", "/health/ready/"),
        ("https://amaris-mathematics-academy-staging-x4ax.onrender.com", "/health/ready"),
    )
    for base, path in health_routes:
        with urllib.request.build_opener(NoRedirect()).open(
            base + path, timeout=30
        ) as response:
            if response.status != 200:
                raise RuntimeError("Staging readiness failed")
        print("PASS staging readiness:", base + path, flush=True)
    print(
        "PASS staging deployment complete; production was not changed by this job",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, KeyError, ValueError, urllib.error.URLError):
        # Never print provider response bodies or exceptions containing DSNs.
        print(
            "Staging deployment blocked or failed; review deployment state and prior check output. No production deployment performed.",
            flush=True,
        )
        raise SystemExit(1) from None
