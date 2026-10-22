"""Verify required contact fields without delivering an enquiry or payment."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument("--frontend", required=True)
parser.add_argument("--backend")
args = parser.parse_args()
os.environ["E2E_BASE_URL"] = args.frontend.rstrip("/")
module_path = Path(__file__).resolve().parents[2] / "frontend/e2e/responsive_browser.py"
spec = importlib.util.spec_from_file_location("contact_browser_checks", module_path)
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)

# Public Render pages load their hydration scripts over the network. Wait for
# loading to settle before testing the interactive inline error handlers.
original_goto = checks.goto
def ready_goto(page, path):
    original_goto(page, path)
    page.wait_for_load_state("networkidle", timeout=60000)
checks.goto = ready_goto

from playwright.sync_api import sync_playwright

with sync_playwright() as playwright:
    configurations = [(engine, name, {"viewport": viewport}) for engine in ("chromium", "firefox", "webkit") for name, viewport in checks.VIEWPORTS.items()]
    for name in checks.NAMED_DEVICES:
        descriptor = dict(playwright.devices[name])
        engine = descriptor.pop("default_browser_type")
        configurations.append((engine, name, descriptor))
    for engine, name, options in configurations:
        browser = getattr(playwright, engine).launch(headless=True)
        context = browser.new_context(**options, locale="en-ZA", timezone_id="Africa/Johannesburg")
        page = context.new_page()
        page.set_default_timeout(30000)
        posts = []
        def guard(route):
            if route.request.method == "POST":
                posts.append(route.request.url)
                route.abort()
            else:
                route.continue_()
        page.route("**/contact*", guard)
        try:
            checks.check_contact_required_fields(page)
            assert not posts, "Incomplete contact form attempted a POST"
            assert page.locator("#consent").is_checked()
            assert page.locator("#phone").input_value() == "0710000000"
            assert page.locator("#phone").evaluate("element => element.form.checkValidity()"), "Corrected form is still invalid"
            checks.assert_no_horizontal_overflow(page, "required contact fields")
            print(f"PASS {engine}/{name}: six named prompts, whitespace rejection, retained input and correction; zero contact POSTs", flush=True)
        except Exception:
            page.screenshot(path=str(checks.ARTIFACT_DIR / f"contact-{engine}-{name.replace(' ', '-')}-failure.png"), full_page=True)
            raise
        finally:
            context.close()
            browser.close()
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()
    for path in ("/", "/contact", "/courses", "/login"):
        response = page.goto(args.frontend.rstrip("/") + path, wait_until="domcontentloaded", timeout=60000)
        assert response and response.status == 200, f"Frontend smoke failed: {path}"
        print(f"PASS frontend HTTP 200 {path}", flush=True)
    browser.close()

if args.backend:
    base = args.backend.rstrip("/")
    for path in ("/health/ready/", "/health/version/", "/api/v1/bootstrap/"):
        with urllib.request.urlopen(base + path, timeout=60) as response:
            assert response.status == 200
        print(f"PASS backend HTTP 200 {path}", flush=True)
    required = {"name": "Please enter your full name.", "email": "Please enter your email address.", "phone": "Please enter your phone number.", "subject": "Please choose an enquiry type.", "message": "Please enter your message."}
    for payload in ({}, {field: "   " for field in required}):
        request = urllib.request.Request(base + "/api/v1/enquiries/", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raise AssertionError(f"Incomplete enquiry was accepted: {response.status}")
        except urllib.error.HTTPError as error:
            assert error.code == 400, f"Expected 400; got {error.code}"
            data = json.loads(error.read())
            assert set(data) == set(required), data
            for field, prompt in required.items():
                assert data[field][0] == prompt, (field, data[field])
        print("PASS backend HTTP 400: all five named missing-field prompts; no valid enquiry submitted", flush=True)
