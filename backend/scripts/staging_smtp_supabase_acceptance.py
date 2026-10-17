"""Explicit staging-only proof: Django SMTP PDF attachment and private Supabase S3 round-trip.

Refuses production project and does NOT represent or process a payment.
Run only with a separate staging Supabase project and staging SMTP secrets.
"""
from __future__ import annotations

import hashlib
import os
import re
import uuid
from io import BytesIO
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from django.core.mail import EmailMultiAlternatives
from reportlab.pdfgen import canvas

PRODUCTION_PROJECT = "epkcuseloinygkakxxdu"
TARGET = "bethuelmoukangwe8@gmail.com"


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"MISSING_STAGING_SECRET: {name}")
    return value


project_ref = required("AMARIS_STAGING_SUPABASE_PROJECT_REF")
endpoint = required("AMARIS_STAGING_S3_ENDPOINT")
bucket = required("AMARIS_STAGING_STUDENT_BUCKET")
user = required("AMARIS_STAGING_S3_ACCESS_KEY_ID")
password = required("AMARIS_STAGING_S3_SECRET_ACCESS_KEY")
sender = required("AMARIS_STAGING_SMTP_FROM")
smtp_host = required("AMARIS_STAGING_SMTP_HOST")
smtp_user = required("AMARIS_STAGING_SMTP_USERNAME")
smtp_password = required("AMARIS_STAGING_SMTP_PASSWORD")

if project_ref == PRODUCTION_PROJECT or not re.fullmatch(r"[a-z0-9]{20}", project_ref):
    raise RuntimeError("STAGING_S3_ISOLATION_FAILURE: dedicated non-production project required")
url = urlparse(endpoint)
if url.scheme != "https" or url.hostname != f"{project_ref}.storage.supabase.co":
    raise RuntimeError("STAGING_S3_ISOLATION_FAILURE: S3 endpoint must match staging project")
if not bucket or bucket.lower() in {"amaris-cms-files"}:
    raise RuntimeError("STAGING_S3_ISOLATION_FAILURE: student bucket required")
if "@" not in sender or not smtp_host:
    raise RuntimeError("Invalid staging email configuration")
if smtp_host in {"localhost", "127.0.0.1"}:
    raise RuntimeError("A real SMTP provider is required")

test_id = f"staging-proof-{os.environ['GITHUB_RUN_ID']}-{uuid.uuid4().hex[:9]}"
buffer = BytesIO()
pdf = canvas.Canvas(buffer)
pdf.setTitle(test_id)
pdf.setFont("Helvetica-Bold", 16)
pdf.drawString(55, 740, "Amaris Mathematics Academy")
pdf.setFont("Helvetica", 12)
pdf.drawString(55, 707, "STAGING TEST DOCUMENT - NOT A PAYMENT RECEIPT")
pdf.drawString(55, 683, "No charge was made. Amount: R0.00")
pdf.drawString(55, 659, f"Test reference: {test_id}")
pdf.save()
data = buffer.getvalue()
assert data.startswith(b"%PDF-")
digest = hashlib.sha256(data).hexdigest()
path = f"{uuid.uuid4()}/invoices/{test_id}.pdf"

client = boto3.client(
    "s3",
    endpoint_url=endpoint,
    aws_access_key_id=user,
    aws_secret_access_key=password,
    region_name="us-east-1",
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)
try:
    client.put_object(Bucket=bucket, Key=path, Body=data, ContentType="application/pdf")
    readback = client.get_object(Bucket=bucket, Key=path)["Body"].read()
    assert hashlib.sha256(readback).hexdigest() == digest
    print("STAGING_SUPABASE_PRIVATE_S3_UPLOAD_READBACK=PASS")
finally:
    try:
        client.delete_object(Bucket=bucket, Key=path)
        print("STAGING_SUPABASE_TEST_OBJECT_CLEANUP=PASS")
    except Exception as exc:
        raise RuntimeError("Staging probe object cleanup failed; manually remove staging test object") from exc

os.environ["EMAIL_BACKEND"] = "django.core.mail.backends.smtp.EmailBackend"
from django.conf import settings

settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
settings.EMAIL_HOST = smtp_host
settings.EMAIL_PORT = int(os.environ.get("AMARIS_STAGING_SMTP_PORT", "587"))
settings.EMAIL_HOST_USER = smtp_user
settings.EMAIL_HOST_PASSWORD = smtp_password
settings.EMAIL_USE_TLS = os.environ.get("AMARIS_STAGING_SMTP_USE_TLS", "true").lower() == "true"
settings.EMAIL_USE_SSL = not settings.EMAIL_USE_TLS and settings.EMAIL_PORT == 465
settings.DEFAULT_FROM_EMAIL = sender
settings.EMAIL_TIMEOUT = 20

email = EmailMultiAlternatives(
    subject=f"Amaris staging SMTP invoice probe — {test_id}",
    body=(
        "AMARIS STAGING EMAIL RECEIPT TRANSPORT TEST\n"
        "An actual staging SMTP provider is sending this PDF to the test recipient.\n"
        "NO PAYFAST PAYMENT WAS MADE. THIS IS NOT A PAID INVOICE.\n"
        f"Reference: {test_id}\n"
    ),
    from_email=sender,
    to=[TARGET],
)
email.attach(f"{test_id}.pdf", data, "application/pdf")
sent = email.send(fail_silently=False)
if sent != 1:
    raise RuntimeError("SMTP backend did not accept the test invoice message")
print("STAGING_DJANGO_SMTP_PROVIDER_ACCEPTED=PASS")
print("STAGING_TEST_REFERENCE=" + test_id)
print("STAGING_PDF_SHA256=" + digest)
print("STAGING_RECEIPT_ACCEPTANCE_REQUIRES_GMAIL_INBOX_INSPECTION=YES")
