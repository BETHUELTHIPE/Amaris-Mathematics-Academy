"""Isolated browser journey: real frontend/Django, fake Auth provider, file-captured mail.

Requires a Render/Nitro build and the matching backend feature checkout.
No production credentials, database, storage or inbox are used.
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

import jwt
from playwright.sync_api import sync_playwright

FRONTEND = Path(__file__).resolve().parents[1]
BACKEND = Path(os.environ["TUTOR_BACKEND_ROOT"]).resolve()
ARTIFACTS = Path(os.getenv("TUTOR_E2E_ARTIFACTS", "/tmp/amaris-tutor-browser-evidence"))
ARTIFACTS.mkdir(parents=True, exist_ok=True)
SITE = "http://127.0.0.1:3010"
AUTH = "http://127.0.0.1:3012"
USER_ID = str(uuid.uuid4())
USER = {
    "id": USER_ID, "email": "synthetic.applicant@example.test", "aud": "authenticated", "role": "authenticated",
    "email_confirmed_at": "2026-10-15T00:00:00Z", "confirmed_at": "2026-10-15T00:00:00Z",
    "created_at": "2026-10-15T00:00:00Z", "app_metadata": {"provider": "email"},
    "user_metadata": {"first_name": "Synthetic", "last_name": "Applicant"}, "identities": [],
}
TOKEN = jwt.encode({"sub": USER_ID, "email": USER["email"], "aud": "authenticated", "role": "authenticated",
                    "iss": AUTH + "/auth/v1", "iat": int(time.time()), "exp": int(time.time()) + 3600,
                    "user_metadata": USER["user_metadata"]}, secrets.token_urlsafe(64), algorithm="HS256")


class FakeAuth(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def reply(self, data, status=200):
        raw = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path.startswith("/auth/v1/user") and self.headers.get("Authorization") == "Bearer " + TOKEN:
            self.reply(USER)
        else:
            self.reply({"message": "Invalid synthetic session"}, 401)

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
        if self.path.startswith("/auth/v1/signup"):
            assert data["email"] == USER["email"]
            assert {key: data["data"][key] for key in ("country", "province", "city")} == {"country": "ZA", "province": "Gauteng", "city": "Pretoria"}
            self.reply({"user": {**USER, "email_confirmed_at": None}, "session": None})
        elif self.path.startswith("/auth/v1/verify") and data.get("token") == "123456":
            self.reply(self.session())
        elif self.path.startswith("/auth/v1/token"):
            assert data["email"] == USER["email"]
            self.reply(self.session())
        elif self.path.startswith("/auth/v1/resend"):
            self.reply({})
        else:
            self.reply({"message": "Invalid synthetic request"}, 400)

    def session(self):
        return {"access_token": TOKEN, "refresh_token": "synthetic-refresh", "token_type": "bearer", "expires_in": 3600,
                "expires_at": int(time.time()) + 3600, "user": USER}


def wait(url, process):
    for _ in range(60):
        if process.poll() is not None:
            raise RuntimeError(f"Test service exited with code {process.returncode}")
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("Test service did not become ready")


def audit(page, label):
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2"), f"Overflow: {label}"
    page.add_script_tag(path=str(FRONTEND / "node_modules/axe-core/axe.min.js"))
    findings = page.evaluate("async () => (await axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a','wcag2aa','wcag21aa','wcag22aa']}})).violations.map(v => ({id:v.id, nodes:v.nodes.map(n=>n.target)}))")
    assert not findings, f"Accessibility: {label}: {findings}"


with tempfile.TemporaryDirectory(prefix="amaris-tutor-e2e-") as scratch:
    root = Path(scratch)
    settings_file = root / "tutor_e2e_settings.py"
    settings_file.write_text(
        "from amaris_cms.settings import *\n"
        "DEBUG = True\nSECURE_SSL_REDIRECT = False\nSESSION_COOKIE_SECURE = False\n"
        "ALLOWED_HOSTS = ['127.0.0.1', 'localhost']\n"
        f"DATABASES = {{'default': {{'ENGINE': 'django.db.backends.sqlite3', 'NAME': {str(root / 'database.sqlite3')!r}}}}}\n"
        "CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}, 'public_content': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}\n"
        "EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'\n"
        f"EMAIL_FILE_PATH = {str(root / 'mail')!r}\n"
        f"STORAGES['tutor_qualifications'] = {{'BACKEND': 'django.core.files.storage.FileSystemStorage', 'OPTIONS': {{'location': {str(root / 'qualifications')!r}}}}}\n"
        "CELERY_BROKER_URL = 'memory://'\n"
    )
    environment = {**os.environ, "DJANGO_SETTINGS_MODULE": "tutor_e2e_settings", "PYTHONPATH": str(root) + os.pathsep + str(BACKEND),
                   "DJANGO_SECRET_KEY": secrets.token_urlsafe(64), "DJANGO_DEBUG": "true", "SUPABASE_URL": AUTH,
                   "SUPABASE_PUBLISHABLE_KEY": "synthetic-publishable-key", "SITE_URL": SITE,
                   "CMS_API_URL": "http://127.0.0.1:3011/api/v1", "HOST": "127.0.0.1", "PORT": "3010"}
    auth = ThreadingHTTPServer(("127.0.0.1", 3012), FakeAuth)
    threading.Thread(target=auth.serve_forever, daemon=True).start()
    services = []
    log = (ARTIFACTS / "services.log").open("w")
    try:
        subprocess.run([sys.executable, "manage.py", "migrate", "--noinput"], cwd=BACKEND, env=environment, stdout=log, stderr=log, check=True)
        django = subprocess.Popen([sys.executable, "manage.py", "runserver", "127.0.0.1:3011", "--noreload"], cwd=BACKEND, env=environment, stdout=log, stderr=log)
        services.append(django)
        wait("http://127.0.0.1:3011/health/live/", django)
        frontend = subprocess.Popen(["node", ".output/server/index.mjs"], cwd=FRONTEND, env={**environment, "NODE_ENV": "production"}, stdout=log, stderr=log)
        services.append(frontend)
        wait(SITE + "/tutor/apply", frontend)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.environ.get("TUTOR_CHROME_PATH"), args=["--no-sandbox", "--disable-dev-shm-usage"])
            for width in [320, 390, 834, 1440]:
                context = browser.new_context(viewport={"width": width, "height": 1000})
                page = context.new_page()
                page.goto(SITE + "/tutor/apply", wait_until="networkidle")
                page.get_by_role("heading", name="Share your knowledge.").wait_for()
                audit(page, f"Recruitment {width}")
                page.goto(SITE + "/tutor/register", wait_until="networkidle")
                audit(page, f"Registration {width}")
                if width == 390:
                    page.screenshot(path=str(ARTIFACTS / "registration-mobile.png"), full_page=True)
                context.close()
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()
            page.goto(SITE + "/tutor/register", wait_until="networkidle")
            page.get_by_label("First name", exact=True).fill("Synthetic")
            page.get_by_label("Last name", exact=True).fill("Applicant")
            page.get_by_label("Email address", exact=True).fill(USER["email"])
            page.get_by_label("Password", exact=True).fill("Synthetic-Test-927!")
            page.get_by_label("Confirm password", exact=True).fill("Synthetic-Test-927!")
            page.locator("#country").select_option("ZA")
            page.locator("#province").select_option("Gauteng")
            page.locator("#city").select_option("Pretoria")
            page.locator('input[name="consent"]').check()
            page.get_by_role("button", name="Create applicant account").click()
            page.wait_for_url("**/tutor/verify-email?**")
            page.get_by_label("Six-digit verification code").fill("123456")
            page.get_by_role("button", name="Verify and continue to application").click()
            page.wait_for_url("**/tutor/apply")
            page.get_by_role("button", name="Submit tutor application", exact=True).wait_for()
            audit(page, "Application form desktop")
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(path=str(ARTIFACTS / "application-desktop.png"), full_page=True)
            context.close()
            # A fresh browser session explicitly tests applicant email/password login.
            context = browser.new_context(viewport={"width": 390, "height": 844})
            page = context.new_page()
            page.goto(SITE + "/tutor/apply/login", wait_until="networkidle")
            page.get_by_label("Email address", exact=True).fill(USER["email"])
            page.get_by_label("Password", exact=True).fill("Synthetic-Test-927!")
            page.get_by_role("button", name="Sign in to your application").click()
            page.wait_for_url("**/tutor/apply")
            page.get_by_role("button", name="Submit tutor application", exact=True).wait_for()
            audit(page, "Application form mobile")
            values = {"phone": "0710000000", "qualification": "BSc Mathematics",
                      "institution": "Synthetic University", "subjects": "Mathematics", "levels": "Grade 12",
                      "experience_years": "3", "teaching_experience": "Three years of mathematics tutoring.",
                      "availability": "Weekday evenings in SAST with Zoom and stable internet.",
                      "motivation": "I enjoy helping students understand mathematics and build confidence."}
            for name, value in values.items():
                page.locator(f'[name="{name}"]').fill(value)
            page.locator("#country").select_option("ZA")
            page.locator("#province").select_option("Gauteng")
            page.locator("#city").select_option("Pretoria")
            page.locator('input[name="programmes"][value="caps"]').check()
            page.locator('input[name="documents"]').set_input_files({"name": "qualification.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.7\nsynthetic browser qualification\n%%EOF"})
            page.locator('input[name="consent"]').check()
            page.get_by_role("button", name="Submit tutor application", exact=True).click()
            page.get_by_role("heading", name="Application received", exact=True).wait_for(timeout=45000)
            audit(page, "Application receipt mobile")
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(path=str(ARTIFACTS / "receipt-mobile.png"), full_page=True)
            reference = page.locator("strong").filter(has_text="AMARIS-TUTOR-").inner_text()
            assert page.get_by_text("Your acknowledgement email has been sent.", exact=False).is_visible()
            with page.expect_download() as download_info:
                page.get_by_role("link", name="qualification.pdf", exact=True).click()
            download = download_info.value
            assert download.suggested_filename == "qualification.pdf"
            assert Path(download.path()).read_bytes().startswith(b"%PDF-")
            messages = [BytesParser(policy=policy.default).parsebytes(path.read_bytes()) for path in (root / "mail").glob("*")]
            assert len(messages) == 1
            message = messages[0]
            assert "Amaris tutor application received" in str(message["Subject"])
            assert reference in message.get_body(preferencelist=("plain",)).get_content()
            assert USER["email"] in str(message["To"])
            assert not list(message.iter_attachments())
            assert len(list((root / "qualifications").rglob("*.pdf"))) == 1
            with sqlite3.connect(root / "database.sqlite3") as connection:
                assert connection.execute("SELECT country, province, city FROM content_tutorapplication").fetchall() == [("ZA", "Gauteng", "Pretoria")]
            context.close()
            browser.close()
        print("PASS: registration → verification → fresh-session login → application → private qualification upload → receipt → captured acknowledgement.")
        print("PASS: Axe WCAG checks and overflow checks at 320/390/834/1440; authenticated desktop/mobile form and mobile receipt.")
        print("Auth is simulated and mail is captured locally; live Supabase/SMTP acceptance remains separate.")
    finally:
        for process in reversed(services):
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        auth.shutdown()
        log.close()
