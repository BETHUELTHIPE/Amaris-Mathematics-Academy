"""Verify a *real* PayFast-sandbox-backed Django live-class invoice and SMTP delivery.

This guarded acceptance DOES NOT create a booking, impersonate a gateway, fake an
ITN, or mark a payment as paid. A real sandbox checkout and provider notification
must already have happened, and a dedicated staging student must exist.
The real Django live-class confirmation task supplies the email and PDF.

The runner manually invokes a task; it does not verify autonomous Celery
scheduling. Automatic worker delivery needs separate operational evidence.
"""
from __future__ import annotations

import argparse
import email
import hashlib
import imaplib
import json
import os
import re
import ssl
import sys
import time
from datetime import datetime, timedelta, timezone
from email import policy
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

STAGING_REF = "atyhhjwwxgzeurnwayay"
PRODUCTION_REF = "epkcuseloinygkakxxdu"
STAGING_BACKEND_HOST = "amaris-mathematics-academy-staging.onrender.com"
INBOX = "bethuelmoukangwe8@gmail.com"
MAX_PDF_BYTES = 5_000_000


def require(key: str) -> str:
    value = os.getenv(key, "").strip()
    if not value:
        raise RuntimeError(f"Missing protected staging prerequisite: {key}")
    return value


def sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def check_environment() -> tuple[str, str, str]:
    if require("STAGING_RECEIPT_ACCEPTANCE_ENABLED").lower() != "true":
        raise RuntimeError("Real email acceptance must be explicitly enabled.")
    if require("PAYFAST_MODE").lower() != "sandbox" or require("PAYFAST_ENV").lower() != "sandbox":
        raise RuntimeError("Only the genuine PayFast sandbox is permitted.")
    booking_ref = require("STAGING_VERIFIED_BOOKING_REFERENCE")
    if not re.fullmatch(r"LCB-[A-Za-z0-9_-]{8,90}", booking_ref) or "acceptance" in booking_ref.lower():
        raise RuntimeError("A real LCB- booking reference from a completed sandbox checkout is mandatory.")
    provider_id = require("STAGING_PAYFAST_SANDBOX_TRANSACTION_ID")
    if not re.fullmatch(r"[0-9]{6,24}", provider_id):
        raise RuntimeError("PayFast sandbox ITN must expose a numeric real provider transaction ID.")
    if require("STAGING_TEST_STUDENT_EMAIL").lower() != INBOX:
        raise RuntimeError("Staging student must own the approved recipient mailbox.")
    if require("STAGING_GMAIL_IMAP_USER").lower() != INBOX:
        raise RuntimeError("Only the approved Gmail INBOX may be checked.")
    if require("STAGING_SUPABASE_PROJECT_REF") != STAGING_REF:
        raise RuntimeError("Wrong Supabase project. Never use production.")
    supabase_url = require("STAGING_SUPABASE_URL").rstrip("/")
    if urlparse(supabase_url).hostname != STAGING_REF + ".supabase.co":
        raise RuntimeError("Wrong Supabase Auth hostname.")
    api = require("STAGING_API_BASE_URL").rstrip("/")
    if urlparse(api).scheme != "https" or urlparse(api).hostname != STAGING_BACKEND_HOST:
        raise RuntimeError("Wrong Render API hostname.")
    endpoint = urlparse(require("SUPABASE_S3_ENDPOINT_URL"))
    if endpoint.scheme != "https" or endpoint.hostname != STAGING_REF + ".storage.supabase.co":
        raise RuntimeError("Wrong staging storage endpoint.")
    bucket = require("SUPABASE_S3_STUDENT_BUCKET")
    if bucket == require("SUPABASE_S3_ADMIN_BUCKET"):
        raise RuntimeError("Admin and student buckets must be separate.")
    db = urlparse(require("DATABASE_URL"))
    if db.scheme not in ("postgresql", "postgres"):
        raise RuntimeError("Database URL must use PostgreSQL.")
    if PRODUCTION_REF in db.geturl() or (
        STAGING_REF not in (db.username or "") and
        db.hostname != "db." + STAGING_REF + ".supabase.co"
    ):
        raise RuntimeError("The database URL must identify the isolated staging Supabase project.")
    for key in (
        "STAGING_SUPABASE_PUBLISHABLE_KEY",
        "STAGING_TEST_STUDENT_PASSWORD",
        "STAGING_GMAIL_IMAP_APP_PASSWORD",
        "SUPABASE_S3_ACCESS_KEY_ID",
        "SUPABASE_S3_SECRET_ACCESS_KEY",
        "EMAIL_HOST",
        "EMAIL_HOST_USER",
        "EMAIL_HOST_PASSWORD",
        "DEFAULT_FROM_EMAIL",
    ):
        require(key)
    return booking_ref, provider_id, api


def request_json(url: str, *, body: dict | None = None, headers: dict | None = None) -> dict:
    h = {"Accept": "application/json", **(headers or {})}
    data = None if body is None else json.dumps(body).encode()
    if data is not None:
        h["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=h, method="POST" if data is not None else "GET")
    with urlopen(req, timeout=25, context=ssl.create_default_context()) as resp:
        return json.load(resp)


def login_student() -> tuple[str, str]:
    base = require("STAGING_SUPABASE_URL").rstrip("/")
    response = request_json(
        base + "/auth/v1/token?grant_type=password",
        body={"email": INBOX, "password": require("STAGING_TEST_STUDENT_PASSWORD")},
        headers={"apikey": require("STAGING_SUPABASE_PUBLISHABLE_KEY")},
    )
    user = response.get("user") or {}
    if not response.get("access_token") or str(user.get("email", "")).lower() != INBOX or not user.get("id"):
        raise RuntimeError("Staging test student cannot authenticate via Supabase.")
    return str(response["access_token"]), str(user["id"])


def invoice_url(api: str, reference: str) -> str:
    return api + "/api/v1/student/live-classes/bookings/" + quote(reference, safe="") + "/invoice/"


def ensure_not_public(url: str) -> None:
    try:
        with urlopen(url, timeout=20) as resp:
            raise RuntimeError("SECURITY: anonymous student PDF download returned HTTP " + str(resp.status))
    except HTTPError as exc:
        if exc.code not in (401, 403, 404):
            raise RuntimeError("Unexpected response from anonymous student invoice endpoint.") from exc


def download_as_student(url: str, token: str) -> bytes:
    req = Request(url, headers={"Authorization": "Bearer " + token, "Accept": "application/pdf"})
    with urlopen(req, timeout=45, context=ssl.create_default_context()) as resp:
        if resp.status != 200 or "application/pdf" not in resp.headers.get("Content-Type", ""):
            raise RuntimeError("Authenticated student invoice did not return a PDF.")
        pdf = resp.read(MAX_PDF_BYTES + 1)
    if len(pdf) > MAX_PDF_BYTES or not pdf.startswith(b"%PDF-"):
        raise RuntimeError("Authenticated student invoice returned an invalid PDF.")
    return pdf


def find_received_gmail_pdf(reference: str, invoice_number: str, digest: str, started: datetime) -> bool:
    conn = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=20)
    try:
        conn.login(INBOX, require("STAGING_GMAIL_IMAP_APP_PASSWORD"))
        status, _ = conn.select("INBOX", readonly=True)
        if status != "OK":
            raise RuntimeError("Staging Gmail inbox is inaccessible.")
        for _ in range(18):
            status, rows = conn.search(None, "SUBJECT", '"' + reference + '"')
            if status != "OK":
                raise RuntimeError("Gmail INBOX search failed.")
            for msg_id in rows[0].split()[-15:]:
                status, parts = conn.fetch(msg_id, "(RFC822)")
                if status != "OK" or not parts or not isinstance(parts[0], tuple):
                    continue
                msg = email.message_from_bytes(parts[0][1], policy=policy.default)
                if str(msg.get("Subject", "")) != "Amaris live class confirmed — " + reference:
                    continue
                if INBOX not in str(msg.get("To", "")).lower():
                    continue
                if msg.get("Date"):
                    sent = parsedate_to_datetime(str(msg["Date"]))
                    if sent.tzinfo is None:
                        sent = sent.replace(tzinfo=timezone.utc)
                    if sent < started - timedelta(minutes=2):
                        continue
                body = msg.get_body(preferencelist=("plain",))
                if body is None or invoice_number not in body.get_content() or reference not in msg["Subject"]:
                    continue
                for part in msg.walk():
                    if part.get_content_disposition() != "attachment" or part.get_filename() != invoice_number + ".pdf":
                        continue
                    raw = part.get_payload(decode=True)
                    if raw is None or not raw.startswith(b"%PDF-"):
                        continue
                    if sha256(raw) != digest:
                        raise RuntimeError("Gmail invoice PDF differs from private student storage.")
                    return True
            time.sleep(10)
        return False
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def run_acceptance() -> None:
    reference, payfast_id, api = check_environment()
    token, student_id = login_student()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")
    import django
    django.setup()
    from django.conf import settings
    from django.core.files.storage import storages
    from content.models import LiveClassBooking
    from content.services.invoices import archive_invoice_pdf, student_invoice_key
    from content.tasks import deliver_live_class_confirmation

    if settings.EMAIL_BACKEND != "django.core.mail.backends.smtp.EmailBackend":
        raise RuntimeError("Django's real SMTP email backend must be active.")
    private = storages["student_private"]
    if "S3" not in type(private).__name__:
        raise RuntimeError("Real Supabase S3-backed student storage required.")
    if private.bucket_name != require("SUPABASE_S3_STUDENT_BUCKET"):
        raise RuntimeError("Wrong student private storage bucket.")

    booking = LiveClassBooking.objects.select_related("student", "slot", "slot__tutor").filter(
        reference=reference,
        student__email__iexact=INBOX,
        student__supabase_user_id=student_id,
        status=LiveClassBooking.Status.CONFIRMED,
        paid_at__isnull=False,
        gateway_verified_at__isnull=False,
        invoice_number__isnull=False,
        provider_reference=payfast_id,
        confirmation_sent_at__isnull=True,
    ).first()
    if booking is None or not booking.invoice_number:
        raise RuntimeError("No unpaid-email booking with matching server-verified sandbox payment and student.")
    if booking.amount <= 0 or booking.hold_expires_at is None:
        raise RuntimeError("Invalid verified booking facts.")
    if LiveClassBooking.objects.filter(
        status=LiveClassBooking.Status.CONFIRMED, confirmation_sent_at__isnull=True
    ).exclude(pk=booking.pk).exists():
        raise RuntimeError("Other pending confirmations exist: refuse to send unrelated student email.")

    url = invoice_url(api, reference)
    ensure_not_public(url)
    downloaded = download_as_student(url, token)
    key = student_invoice_key(booking.student.supabase_user_id, booking.invoice_number)
    archived_pdf = archive_invoice_pdf(booking, storage=private)
    if not private.exists(key):
        raise RuntimeError("Student-owned invoice missing from private Supabase storage.")
    with private.open(key, "rb") as stream:
        stored_pdf = stream.read(MAX_PDF_BYTES + 1)
    if not stored_pdf.startswith(b"%PDF-") or len(stored_pdf) > MAX_PDF_BYTES:
        raise RuntimeError("Private Supabase student invoice is not a valid PDF.")
    digest = sha256(stored_pdf)
    if digest != sha256(downloaded) or digest != sha256(archived_pdf):
        raise RuntimeError("Dashboard and private Supabase invoice PDFs differ.")

    started = datetime.now(timezone.utc)
    if deliver_live_class_confirmation.run() != 1:
        raise RuntimeError("Django real booking confirmation task failed to deliver exactly one email.")
    booking.refresh_from_db()
    if booking.confirmation_sent_at is None:
        raise RuntimeError("Django did not record SMTP acceptance.")
    if not find_received_gmail_pdf(reference, booking.invoice_number, digest, started):
        raise RuntimeError("Django SMTP sent mail but matching PDF did not arrive in Gmail INBOX.")

    evidence = {
        "staging_booking_reference": reference,
        "sandbox_provider_transaction_id_last4": payfast_id[-4:],
        "invoice_number": booking.invoice_number,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "real_django_smtp_booking_email": True,
        "matching_gmail_inbox_attachment": True,
        "student_owned_private_pdf": True,
        "authenticated_dashboard_pdf_matches": True,
        "anonymous_pdf_access_denied": True,
        "automated_background_celery_worker_verified": False,
        "pdf_sha256": digest,
        "pdf_bytes": len(stored_pdf),
    }
    Path("/tmp/amaris-staging-liveclass-acceptance.json").write_text(json.dumps(evidence, indent=2))
    print("STAGING_DJANGO_LIVECLASS_RECEIPT=PASS")
    print("AUTONOMOUS_CELERY_DELIVERY=NOT_VERIFIED")
    print("PDF_SHA256=" + digest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--syntax-only", action="store_true")
    args = parser.parse_args()
    if args.syntax_only:
        print("STAGING_LIVECLASS_RECEIPT_SCRIPT=SYNTAX_OK; REAL_ACCEPTANCE_NOT_ATTEMPTED")
        sys.exit(0)
    try:
        run_acceptance()
    except (RuntimeError, HTTPError, URLError, OSError, ValueError, AssertionError) as exc:
        # External errors may include credentials or tokens; only print the class.
        print("STAGING_DJANGO_LIVECLASS_RECEIPT=BLOCKED; " + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
