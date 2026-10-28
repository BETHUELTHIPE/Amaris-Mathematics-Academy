"""Real Chromium acceptance of the private Amaris PDF invoice download.

Requires an existing verified staging student with protected login credentials.
The invoice reference is discovered from that student's private Orders page.
Never creates an account, issues a payment, or changes a booking.
"""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urljoin, urlsplit

from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError, sync_playwright

URL = os.environ.get(
    "STAGING_STUDENT_URL",
    "https://amaris-mathematics-academy-staging-x4ax.onrender.com",
).rstrip("/")
EMAIL = os.environ.get("STAGING_TEST_STUDENT_EMAIL", "")
PASSWORD = os.environ.get("STAGING_TEST_STUDENT_PASSWORD", "")

missing = [
    name for name, value in (
        ("STAGING_TEST_STUDENT_EMAIL", EMAIL),
        ("STAGING_TEST_STUDENT_PASSWORD", PASSWORD),
    ) if not value
]
if not URL.startswith("https://"):
    raise SystemExit("BLOCK: invalid staging URL")
anonymous_invoice_url = (
    f"{URL}/book-online-live-class/invoice?reference=LCB-anonymous-security-probe"
)

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    try:
        # The unauthenticated browser must not receive invoice PDF bytes.
        anonymous = browser.new_context(accept_downloads=True)
        anon_response = anonymous.request.get(anonymous_invoice_url, max_redirects=0, timeout=30000)
        if anon_response.status not in (302, 303, 307, 308, 401, 403, 404):
            raise AssertionError("BLOCK: unauthenticated invoice URL did not deny access")
        if "application/pdf" in (anon_response.headers.get("content-type") or "").lower():
            raise AssertionError("BLOCK: an anonymous browser received an invoice")
        print("PASS: Anonymous browser cannot download private invoice")

        if missing:
            raise SystemExit(
                "BLOCK: protected staging QA secrets absent: " + ", ".join(missing)
                + ". No authenticated download was attempted."
            )
        # Only a genuine, confirmed staging account may supply the browser cookie.
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.goto(f"{URL}/login", wait_until="domcontentloaded", timeout=45000)
        page.locator('form:has(button:has-text("Log in securely")) input[name="email"]').fill(EMAIL)
        page.locator('form:has(button:has-text("Log in securely")) input[name="password"]').fill(PASSWORD)
        page.get_by_role("button", name="Log in securely").click()
        try:
            page.wait_for_url("**/dashboard**", wait_until="domcontentloaded", timeout=45000)
        except PlaywrightTimeoutError:
            current = urlsplit(page.url)
            if current.path.rstrip("/") == "/login" and "error" in parse_qs(current.query):
                raise SystemExit(
                    "BLOCK: staging rejected the protected QA login. Verify the staging "
                    "account and update its protected environment credentials. "
                    "No authenticated invoice download was attempted."
                ) from None
            raise SystemExit(
                "BLOCK: staging login did not reach the student dashboard. "
                "No authenticated invoice download was attempted."
            ) from None
        auth_state = context.request.get(f"{URL}/api/auth-state", timeout=30000)
        if auth_state.status != 200:
            raise AssertionError("BLOCK: authenticated student state unavailable")
        state = auth_state.json()
        if not state.get("authenticated") or not state.get("emailVerified"):
            raise AssertionError("BLOCK: student is not authoritatively email-verified")
        print("PASS: Browser session is authenticated with verified student email")

        # Discover the reference from the authenticated student's own Orders.
        # Never store private booking identifiers in public repository code.
        page.goto(f"{URL}/dashboard/orders", wait_until="domcontentloaded", timeout=60000)
        owned_invoice = page.locator(
            'a[href^="/book-online-live-class/invoice?reference="]'
        ).first
        link = owned_invoice
        try:
            link.wait_for(state="visible", timeout=20000)
        except Exception:
            raise SystemExit(
                "BLOCK: verified staging student has no visible confirmed live-class invoice"
            ) from None
        href = link.get_attribute("href") or ""
        if not href.startswith("/book-online-live-class/invoice?reference="):
            raise AssertionError("BLOCK: invoice link is not a private live-class route")
        invoice_url = urljoin(URL, href)

        # The anonymous browser must also be rejected for this exact owned invoice.
        blocked = anonymous.request.get(invoice_url, max_redirects=0, timeout=45000)
        if blocked.status not in (302, 303, 307, 308, 401, 403, 404):
            raise AssertionError("BLOCK: anonymous browser accessed a real student's invoice")
        if "application/pdf" in (blocked.headers.get("content-type") or "").lower():
            raise AssertionError("BLOCK: anonymous browser received a real invoice PDF")
        print("PASS: Anonymous browser denied exact student-owned invoice")
        anonymous.close()

        # Click the actual user-facing download button in a real browser session.
        with page.expect_download(timeout=45000) as event:
            link.click()
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
    except PlaywrightError:
        # Browser errors may include private URLs or entered form values.
        raise SystemExit(
            "BLOCK: browser acceptance could not complete. "
            "Browser details suppressed to protect student data."
        ) from None
    finally:
        browser.close()
