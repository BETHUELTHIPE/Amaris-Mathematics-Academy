"""Real tutor UI on candidate Nitro, authenticated against deployed staging Django.

Run only from protected GitHub staging environment, on a pinned reviewed commit.
No screenshots, HAR, JWT output, raw API bodies, slot changes, purchases or payouts.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

STAGING_BACKEND = "https://amaris-mathematics-academy-staging.onrender.com"
STAGING_AUTH = "https://atyhhjwwxgzeurnwayay.supabase.co"
LOCAL = "http://127.0.0.1:38117"
ROOT = Path(__file__).resolve().parents[1]


def require(name: str) -> str:
    value = os.environ.get(name, "")
    if len(value) < 2 or "\r" in value or "\n" in value:
        raise RuntimeError(f"BLOCK: protected staging setting {name} missing")
    return value


def guard() -> tuple[str, str, str]:
    if os.environ.get("GITHUB_REPOSITORY") != "BETHUELTHIPE/Amaris-Mathematics-Academy":
        raise RuntimeError("BLOCK: incorrect GitHub repository")
    if os.environ.get("GITHUB_REF") != "refs/heads/main":
        raise RuntimeError("BLOCK: authenticated check requires trusted main workflow")
    if os.environ.get("STAGING_TUTOR_UI_CONFIRM") != "RUN_STAGING_TUTOR_UI":
        raise RuntimeError("BLOCK: explicit staging-only tutor browser approval missing")
    if os.environ.get("PAYFAST_MODE") != "sandbox":
        raise RuntimeError("BLOCK: never use real payments")
    if any(os.getenv(key) for key in ("DATABASE_URL", "PAYFAST_MERCHANT_KEY", "PAYFAST_PASSPHRASE", "SUPABASE_SERVICE_ROLE_KEY")):
        raise RuntimeError("BLOCK: browser job received unnecessary privileged secrets")
    if os.environ.get("CMS_API_URL") != STAGING_BACKEND:
        raise RuntimeError("BLOCK: candidate does not target deployed staging backend")
    if os.environ.get("SUPABASE_URL") != STAGING_AUTH:
        raise RuntimeError("BLOCK: candidate does not target staging Supabase Auth")
    email = require("STAGING_TEST_TUTOR_EMAIL").strip().lower()
    password = require("STAGING_TEST_TUTOR_PASSWORD")
    key = require("STAGING_SUPABASE_PUBLISHABLE_KEY")
    if "@" not in email or email.endswith((".invalid", ".example", "@example.com")):
        raise RuntimeError("BLOCK: not a real approved staging QA tutor identity")
    return email, password, key


def verify_ready(server: subprocess.Popen) -> None:
    for _ in range(45):
        if server.poll() is not None:
            raise RuntimeError("BLOCK: candidate Nitro server exited unexpectedly")
        try:
            with urlopen(LOCAL + "/tutor/login", timeout=3) as response:
                if response.status == 200:
                    return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("BLOCK: candidate tutor login page not ready")


def assert_safe_response(response, label: str) -> dict:
    if not response or response.status != 200:
        raise AssertionError(f"{label}: staging tutor API HTTP {response.status if response else 0} (requires approved matching Django tutor)")
    cache_control = (response.headers.get("cache-control") or "").lower()
    if "public" in cache_control or "s-maxage" in cache_control:
        raise AssertionError(f"{label}: private tutor response is publicly cacheable")
    data = response.json()
    if not isinstance(data, dict):
        raise AssertionError(f"{label}: invalid JSON response shape")
    print(f"PASS {label} served by real staging Django (private and authenticated)", flush=True)
    return data


def run_browser(browser, email: str, password: str, key: str):
    context = browser.new_context(
        viewport={"width": 390, "height": 844},
        timezone_id="Africa/Johannesburg", locale="en-ZA", reduced_motion="reduce",
    )
    page = context.new_page()
    page.set_default_timeout(30_000)
    try:
        # Confirm staging backend health and denial before handling any secrets.
        health = context.request.get(STAGING_BACKEND + "/health/ready/", timeout=40000)
        if health.status != 200:
            raise AssertionError(f"BLOCK: deployed staging backend unavailable (HTTP {health.status})")
        anonymous = context.request.get(STAGING_BACKEND + "/api/v1/tutor/dashboard/", timeout=40000)
        if anonymous.status not in (401, 403):
            raise AssertionError("SECURITY: unauthenticated staging tutor dashboard was not denied")
        print("PASS staging backend ready and rejects anonymous tutor reads", flush=True)

        # Browser signs in through the candidate frontend and establishes
        # real cookie-backed SSR session; no synthetic identity or mocked APIs.
        page.goto(LOCAL + "/tutor/login", wait_until="domcontentloaded", timeout=45000)
        page.locator('input[name="email"]').fill(email)
        page.locator('input[name="password"]').fill(password)
        page.get_by_role("button", name="Sign in to tutor dashboard").click()
        page.wait_for_url("**/tutor/dashboard*", timeout=45000)
        page.get_by_role("heading", name="Your teaching slots").wait_for(timeout=45000)
        page.get_by_role("heading", name="Offer a new live Zoom class").wait_for()
        page.get_by_role("button", name="Publish tutor availability").wait_for()
        if page.get_by_text("Tutor service unavailable").count() or page.get_by_text("Tutor access requires approval").count():
            raise AssertionError("BLOCK: genuine staging tutor access was not accepted")
        print("PASS new candidate tutor UI login and timetable backed by real staging Django", flush=True)

        # Independent JWT-based read of that same staging Django service:
        # never print email, JWT, bookings, banking details or response bodies.
        token_reply = context.request.post(
            STAGING_AUTH + "/auth/v1/token?grant_type=password",
            headers={"apikey": key, "Content-Type": "application/json"},
            data=json.dumps({"email": email, "password": password}),
            timeout=40000,
        )
        if token_reply.status != 200:
            raise AssertionError(f"BLOCK: staging Supabase tutor auth HTTP {token_reply.status}")
        token_data = token_reply.json()
        if (token_data.get("user") or {}).get("email", "").lower() != email or not token_data.get("access_token"):
            raise AssertionError("BLOCK: authenticated staging tutor identity mismatch")
        headers = {"Authorization": "Bearer " + token_data["access_token"]}
        dashboard = assert_safe_response(
            context.request.get(STAGING_BACKEND + "/api/v1/tutor/dashboard/", headers=headers, timeout=40000),
            "tutor dashboard")
        assert_safe_response(
            context.request.get(STAGING_BACKEND + "/api/v1/tutor/earnings/", headers=headers, timeout=40000),
            "tutor earnings")
        if not isinstance(dashboard.get("slots"), list) or not isinstance(dashboard.get("bookings"), list):
            raise AssertionError("BLOCK: missing genuine tutor-owned slots or bookings arrays")

        for width, height in ((390, 844), (1440, 900)):
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(150)
            size = page.evaluate("() => ({width:innerWidth,scroll:Math.max(document.body.scrollWidth,document.documentElement.scrollWidth)})")
            if size["scroll"] > size["width"] + 2:
                raise AssertionError(f"FAIL tutor dashboard horizontal overflow at {width}px")
            print(f"PASS new tutor UI at {width}px, no horizontal overflow", flush=True)
        if len(dashboard["slots"]) > 8:
            page.goto(LOCAL + "/tutor/dashboard?slots_page=2", wait_until="domcontentloaded")
            page.get_by_role("heading", name="Your teaching slots").wait_for()
            print("PASS new tutor slots pagination page 2 with real staging data", flush=True)
        else:
            print("NOT VERIFIED slots page 2: test tutor has 8 or fewer records", flush=True)
        if len(dashboard["bookings"]) > 8:
            page.goto(LOCAL + "/tutor/dashboard?bookings_page=2", wait_until="domcontentloaded")
            page.get_by_role("heading", name="Your teaching slots").wait_for()
            print("PASS new tutor bookings pagination page 2 with real staging data", flush=True)
        else:
            print("NOT VERIFIED bookings page 2: test tutor has 8 or fewer records", flush=True)

        page.goto(LOCAL + "/tutor/dashboard", wait_until="domcontentloaded")
        page.get_by_role("heading", name="Your teaching slots").wait_for(timeout=35000)
        print("PASS tutor cookie session survives browser navigation", flush=True)
        print("PASS staging backend connected to candidate tutor UI; no writes", flush=True)
    finally:
        context.close()


def main() -> None:
    email, password, key = guard()
    # Build and binary paths are provisioned by the separately protected workflow.
    logfile = Path("/tmp/amaris-staging-tutor-candidate.log")
    with logfile.open("w") as out:
        server = subprocess.Popen(
            ["node", ".output/server/index.mjs"], cwd=ROOT, stdout=out,
            stderr=subprocess.STDOUT,
            env={
                **os.environ, "PORT": "38117", "HOST": "127.0.0.1",
                "SITE_URL": LOCAL, "NODE_ENV": "production", "NITRO_PORT": "38117",
            },
        )
        try:
            verify_ready(server)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
                try:
                    run_browser(browser, email, password, key)
                finally:
                    browser.close()
        finally:
            server.terminate()
            try:
                server.wait(timeout=8)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == "__main__":
    main()
