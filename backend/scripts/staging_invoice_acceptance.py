"""Fail-closed staging SMTP -> Gmail -> Supabase invoice acceptance.

Run ONLY with separate staging DB/Supabase project, verified sandbox course payment,
a dedicated Supabase student account and protected GitHub staging secrets. This
command does not create a payment, forge an ITN, or change a payment's status.
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
from datetime import datetime, timezone
from email import policy
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


PRODUCTION_PROJECT_REF = "epkcuseloinygkakxxdu"
PRODUCTION_BUCKET = "Amaris Mathematics Academy"
RECEIVER = "bethuelmoukangwe8@gmail.com"
STAGING_BACKEND_HOST = "amaris-mathematics-academy-staging.onrender.com"


def require(name: str) -> str:
    result = os.getenv(name, "").strip()
    if not result:
        raise RuntimeError("Missing required protected staging environment setting: " + name)
    return result


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def check_environment() -> tuple[str, str, str]:
    if require("STAGING_RECEIPT_ACCEPTANCE_ENABLED").lower() != "true":
        raise RuntimeError("Staging acceptance remains disabled.")
    if os.getenv("PAYFAST_ENV", "").lower() != "sandbox":
        raise RuntimeError("Only sandbox-verified test orders are permitted.")
    reference = require("STAGING_VERIFIED_PAYMENT_REFERENCE")
    if not re.fullmatch(r"[A-Za-z0-9_-]{12,100}", reference) or "acceptance" in reference.lower():
        raise RuntimeError("A genuine staging sandbox checkout reference is required.")
    if require("STAGING_TEST_STUDENT_EMAIL").lower() != RECEIVER:
        raise RuntimeError("Staging test student's registered email must equal the approved test inbox.")
    if require("STAGING_GMAIL_IMAP_USER").lower() != RECEIVER:
        raise RuntimeError("The Gmail inbox must be the approved test mailbox.")
    api = require("STAGING_API_BASE_URL").rstrip("/")
    if urlparse(api).scheme != "https" or urlparse(api).hostname != STAGING_BACKEND_HOST:
        raise RuntimeError("Staging API must be the allowlisted staging Render hostname.")

    ref = require("STAGING_SUPABASE_PROJECT_REF")
    supabase_url = require("STAGING_SUPABASE_URL").rstrip("/")
    if (
        ref == PRODUCTION_PROJECT_REF
        or not re.fullmatch(r"[a-z0-9]{20}", ref)
        or urlparse(supabase_url).hostname != ref + ".supabase.co"
    ):
        raise RuntimeError("A separate staging Supabase project is mandatory; production is forbidden.")
    storage_endpoint = require("SUPABASE_S3_ENDPOINT_URL")
    if ref not in urlparse(storage_endpoint).hostname or urlparse(storage_endpoint).scheme != "https":
        raise RuntimeError("The S3 endpoint does not belong to the isolated staging project.")
    if require("SUPABASE_S3_STUDENT_BUCKET") == PRODUCTION_BUCKET:
        raise RuntimeError("Staging must use a separate, private student-document bucket.")
    if not require("SUPABASE_S3_ACCESS_KEY_ID") or not require("SUPABASE_S3_SECRET_ACCESS_KEY"):
        raise RuntimeError("Staging S3 credentials not configured.")
    db = require("DATABASE_URL")
    parsed_db = urlparse(db)
    if (
        "amaris_staging_postgres" not in db
        or PRODUCTION_PROJECT_REF in db
        or "dpg-dapagkpsrm7s73eoaagg-a" in db
        or parsed_db.scheme not in ("postgresql", "postgres")
    ):
        raise RuntimeError("The database must be the isolated Amaris staging database.")
    for name in ("STAGING_TEST_STUDENT_PASSWORD","STAGING_GMAIL_IMAP_APP_PASSWORD",
                 "EMAIL_HOST","EMAIL_HOST_USER","EMAIL_HOST_PASSWORD","DEFAULT_FROM_EMAIL"):
        require(name)
    return reference, api, supabase_url


def get_json(url: str, *, body: dict | None = None, headers: dict | None = None) -> dict:
    headers = {"Accept": "application/json", **(headers or {})}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    with urlopen(req, timeout=25, context=ssl.create_default_context()) as resp:
        return json.load(resp)


def login_student(supabase_url: str) -> tuple[str, str]:
    data = get_json(
        supabase_url + "/auth/v1/token?grant_type=password",
        body={"email": RECEIVER, "password": require("STAGING_TEST_STUDENT_PASSWORD")},
        headers={"apikey": require("STAGING_SUPABASE_PUBLISHABLE_KEY")},
    )
    token = data.get("access_token", "")
    user = data.get("user") or {}
    if not token or user.get("email", "").lower() != RECEIVER or not user.get("id"):
        raise RuntimeError("The dedicated test-student Supabase login failed.")
    return token, str(user["id"])


def fetch_invoice_as_student(api: str, reference: str, token: str) -> bytes:
    url = api + "/api/v1/student/orders/" + quote(reference, safe="") + "/invoice/"
    req = Request(url, headers={"Authorization": "Bearer " + token, "Accept": "application/pdf"})
    with urlopen(req, timeout=45, context=ssl.create_default_context()) as resp:
        if resp.status != 200 or "application/pdf" not in resp.headers.get("Content-Type", ""):
            raise RuntimeError("Authenticated dashboard did not return a PDF.")
        result = resp.read(5_000_001)
        if len(result) > 5_000_000:
            raise RuntimeError("Unexpectedly large staging invoice.")
        if not result.startswith(b"%PDF-"):
            raise RuntimeError("Authenticated download was not a PDF.")
        return result


def ensure_anonymous_denied(api: str, reference: str) -> None:
    url = api + "/api/v1/student/orders/" + quote(reference, safe="") + "/invoice/"
    try:
        with urlopen(url, timeout=20, context=ssl.create_default_context()) as resp:
            raise RuntimeError("SECURITY FAILURE: anonymous invoice download returned " + str(resp.status))
    except HTTPError as exc:
        if exc.code not in (401, 403, 404):
            raise RuntimeError("Anonymous invoice endpoint had unexpected HTTP status.") from exc


def find_gmail_pdf(tag: str, expected_filename: str, expected_digest: str) -> bool:
    # IMAP is restricted to a dedicated acceptance mailbox; credentials are
    # loaded only from the protected GitHub staging environment, never printed.
    conn = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=20)
    try:
        conn.login(RECEIVER, require("STAGING_GMAIL_IMAP_APP_PASSWORD"))
        typ, _ = conn.select("INBOX", readonly=True)
        if typ != "OK":
            raise RuntimeError("The staging test inbox could not be opened.")
        for _ in range(18):
            typ, ids = conn.search(None, 'SUBJECT', '"' + tag + '"')
            if typ != "OK":
                raise RuntimeError("Gmail IMAP search failed.")
            for msg_id in ids[0].split()[-15:]:
                typ, parts = conn.fetch(msg_id, "(RFC822)")
                if typ != "OK" or not parts or not parts[0] or not isinstance(parts[0], tuple):
                    continue
                msg = email.message_from_bytes(parts[0][1], policy=policy.default)
                if tag not in str(msg.get("Subject", "")):
                    continue
                if RECEIVER not in str(msg.get("To", "")).lower():
                    continue
                for part in msg.walk():
                    if part.get_content_disposition() != "attachment":
                        continue
                    if part.get_filename() != expected_filename:
                        continue
                    attachment = part.get_payload(decode=True)
                    if attachment is None:
                        continue
                    if sha(attachment) != expected_digest:
                        raise RuntimeError("Gmail invoice attachment differs from Supabase private PDF.")
                    return True
            time.sleep(10)
        return False
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def run_acceptance() -> None:
    reference, api, supabase_url = check_environment()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")

    # Fail before sending email if student authentication is not working.
    token, student_id = login_student(supabase_url)
    import django
    django.setup()
    from django.conf import settings
    from django.core.files.storage import storages
    from django.core.mail import EmailMultiAlternatives
    from content.models import Payment
    from content.payment_models import Invoice
    from content.services.invoices import archive_invoice_pdf, invoice_storage_path

    if settings.EMAIL_BACKEND != "django.core.mail.backends.smtp.EmailBackend":
        raise RuntimeError("External Django SMTP backend is mandatory.")
    if settings.EMAIL_HOST != require("EMAIL_HOST"):
        raise RuntimeError("Django SMTP configuration does not match staging secrets.")
    private_storage = storages["student_private"]
    if "S3" not in type(private_storage).__name__:
        raise RuntimeError("Student private storage is not Supabase S3.")
    if getattr(private_storage, "bucket_name", "") != require("SUPABASE_S3_STUDENT_BUCKET"):
        raise RuntimeError("Wrong private student bucket.")
    invoice = (
        Invoice.objects.select_related("payment", "student", "course")
        .filter(
            payment__reference=reference,
            payment__status=Payment.Status.PAID,
            payment__gateway_verified_at__isnull=False,
            payment__verification_source="payfast_server_verification",
            student__email__iexact=RECEIVER,
            student__supabase_user_id=student_id,
        )
        .first()
    )
    if invoice is None:
        raise RuntimeError("No authentic provider-verified, student-owned staging invoice.")
    payment = invoice.payment
    if (
        not payment.provider_reference
        or not re.fullmatch(r"[0-9]{6,24}", payment.provider_reference)
        or any(x in payment.provider_reference.lower() for x in ("test", "synthetic"))
    ):
        raise RuntimeError("The payment lacks an authentic numeric PayFast provider reference.")

    pdf = archive_invoice_pdf(invoice, storage=private_storage)
    key = invoice_storage_path(invoice)
    if not private_storage.exists(key):
        raise RuntimeError("Invoice was not archived to the Supabase private student bucket.")
    with private_storage.open(key, "rb") as stream:
        archived = stream.read()
    if not pdf.startswith(b"%PDF-") or sha(pdf) != sha(archived):
        raise RuntimeError("Supabase archived invoice differs from Django's invoice PDF.")

    # Verify actual staging student authorization before sending a test email.
    ensure_anonymous_denied(api, reference)
    downloaded = fetch_invoice_as_student(api, reference, token)
    if sha(downloaded) != sha(archived):
        raise RuntimeError("Authenticated staging dashboard PDF differs from Supabase.")

    tag = "AMARIS-STAGING-INVOICE-" + require("GITHUB_RUN_ID")
    message = EmailMultiAlternatives(
        subject="Amaris STAGING paid invoice acceptance " + tag,
        body=(
            "Staging-only acceptance verification of a PayFast sandbox purchase.\n"
            "This is NOT a new charge. This message is not a tax certificate.\n"
            f"Invoice: {invoice.invoice_number}\nRun: {tag}\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[RECEIVER],
        headers={"X-Amaris-Staging-Acceptance": tag},
    )
    filename = invoice.invoice_number + ".pdf"
    message.attach(filename, archived, "application/pdf")
    if message.send(fail_silently=False) != 1:
        raise RuntimeError("The configured external SMTP provider did not accept the message.")
    if not find_gmail_pdf(tag, filename, sha(archived)):
        raise RuntimeError("External SMTP accepted the message, but Gmail delivery was not verified.")

    evidence = {
        "run_id": require("GITHUB_RUN_ID"),
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "staging_generated_invoice": True,
        "external_smtp_accepted": True,
        "gmail_inbox_attachment_matches": True,
        "supabase_private_storage_matches": True,
        "authenticated_student_dashboard_pdf_matches": True,
        "anonymous_access_rejected": True,
        "attachment_sha256": sha(archived),
        "pdf_size_bytes": len(archived),
    }
    output = Path("/tmp/amaris-staging-invoice-acceptance.json")
    output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print("STAGING_INVOICE_ACCEPTANCE=PASS")
    print("RECEIPT_PDF_SHA256=" + sha(archived))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--syntax-only", action="store_true")
    args = parser.parse_args()
    if args.syntax_only:
        print("STAGING_ACCEPTANCE_SCRIPT_SYNTAX=OK")
        sys.exit(0)
    try:
        run_acceptance()
    except (RuntimeError, HTTPError, URLError, OSError, ValueError, AssertionError) as exc:
        # Do not log exception contents from external providers which may contain
        # query strings, credentials, recipients or Supabase identifiers.
        print("STAGING_INVOICE_ACCEPTANCE=FAIL; stage=" + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
