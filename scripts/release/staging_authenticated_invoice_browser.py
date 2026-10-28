"""Real Chromium acceptance of the private Amaris PDF invoice download.

Requires a verified staging student, their existing password and a genuine paid
booking reference, supplied only as protected GitHub Actions staging secrets.
Never creates an account, issues a payment, or changes a booking.
"""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote

from playwright.sync_api import sync_playwright

URL = os.environ.get(
    "STAGING_STUDENT_URL",
    "https://amaris-mathematics-academy-staging-x4ax.onrender.com",
).rstrip("/")
EMAIL = os.environ.get("STAGING_TEST_STUDENT_EMAIL", "")
PASSWORD = os.environ.get("STAGING_TEST_STUDENT_PASSWORD", "")
BOOKING = os.environ.get("STAGING_TEST_BOOKING_REFERENCE", "")

if not EMAIL or not PASSWORD or not BOOKING:
    raise SystemExit(
        "BLOCK: staging verified-student email, password and genuine paid booking reference "
        "must all exist as protected staging secrets; no fake session is permitted."
    )
if not URL.startswith("https://") or not BOOKING.replace("_", "").replace("-", "").isalnum():
    raise SystemExit("BLOCK: invalid staging URL or booking reference.")

invoice_url = f"{URL}/book-online-live-class/invoice?reference={quote(BOOKING)}"

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    try:
        # The unauthenticated browser must not receive invoice PDF bytes.
        anonymous = browser.new_context(accept_downloads=True)
        anon_response = anonymous.request.get(invoice_url, max_redirects=0, timeout=30000)
        if anon_response.status not in (302, 303, 307, 308, 401, 403, 404):
            raise AssertionError("BLOCK: unauthenticated invoice URL did not deny access")
        if "application/pdf" in (anon_response.headers.get("content-type") or "").lower():
            raise AssertionError("BLOCK: an anonymous browser received an invoice")
        print("PASS: Anonymous browser cannot download private invoice")
        anonymous.close()

        # Only a genuine, confirmed staging account may supply the browser cookie.
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.goto(f"{URL}/login", wait_until="domcontentloaded", timeout=45000)
        page.locator('form:has(button:has-text("Log in securely")) input[name="email"]').fill(EMAIL)
        page.locator('form:has(button:has-text("Log in securely")) input[name="password"]').fill(PASSWORD)
        page.get_by_role("button", name="Log in securely").click()
        page.wait_for_url("**/dashboard**", timeout=45000)
        auth_state = context.request.get(f"{URL}/api/auth-state", timeout=30000)
        if auth_state.status != 200:
            raise AssertionError("BLOCK: authenticated student state unavailable")
        state = auth_state.json()
        if not state.get("authenticated") or not state.get("emailVerified"):
            raise AssertionError("BLOCK: student is not authoritatively email-verified")
        print("PASS: Browser session is authenticated with verified student email")

        # Use actual browser navigation, not an APIClient mock or a forged token.
        with page.expect_download(timeout=45000) as event:
            page.evaluate(
                """url => {
                  const anchor = document.createElement('a');
                  anchor.href = url;
                  anchor.download = '';
                  document.body.appendChild(anchor);
                  anchor.click();
                  anchor.remove();
                }""",
                invoice_url,
            )
        download = event.value
        with TemporaryDirectory() as tmp:
            destination = Path(tmp, "verified-invoice.pdf")
            download.save_as(destination)
            pdf = destination.read_bytes()
            if len(pdf) < 2000 or not pdf.startswith(b"%PDF-"):
                raise AssertionError("BLOCK: browser downloaded invalid PDF bytes")
            if not download.suggested_filename.lower().endswith(".pdf"):
                raise AssertionError("BLOCK: invoice attachment filename missing")
        print("PASS: Verified staging student downloaded real archived PDF in Chromium")
        print("No credentials, session cookies, student details or PDF bytes were logged")
        context.close()
    finally:
        browser.close()
