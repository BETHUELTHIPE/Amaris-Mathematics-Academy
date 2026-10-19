"""Verified payment receipts for isolated staging, never public local-media storage."""
from __future__ import annotations

import io
import os
import re
from urllib.parse import urlparse

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from content.models import LiveClassBooking, Payment
from content.payment_models import Invoice


class StagingReceiptUnavailable(OSError):
    pass


def private_receipt_storage():
    """Fail closed unless the staging bucket is isolated from production."""
    if getattr(settings, "STAGING_RECEIPTS_ALLOW_LOCAL_TEST_STORAGE", False):
        return storages["student_data"]
    if not getattr(settings, "STAGING_RECEIPTS_ENABLED", False):
        raise StagingReceiptUnavailable("Private staging invoice storage is disabled.")
    project = str(getattr(settings, "STAGING_SUPABASE_PROJECT_REF", "")).strip()
    if not re.fullmatch(r"[a-z0-9]{20}", project) or project == "epkcuseloinygkakxxdu":
        raise StagingReceiptUnavailable("A separate staging Supabase project is required.")
    bucket = str(getattr(settings, "STUDENT_STORAGE_BUCKET_NAME", "")).strip()
    cms_bucket = str(getattr(settings, "CMS_STORAGE_BUCKET_NAME", "")).strip()
    endpoint = str(getattr(settings, "AWS_S3_ENDPOINT_URL", "")).strip()
    parsed = urlparse(endpoint)
    if (
        not bucket
        or bucket == cms_bucket
        or not cms_bucket
        or parsed.scheme != "https"
        or parsed.hostname not in {f"{project}.storage.supabase.co", f"{project}.supabase.co"}
        or not parsed.path.rstrip("/").endswith("/storage/v1/s3")
    ):
        raise StagingReceiptUnavailable("Staging private storage configuration is invalid.")
    from storages.backends.s3 import S3Storage

    storage = storages["student_data"]
    if not isinstance(storage, S3Storage):
        raise StagingReceiptUnavailable("Private receipts require a configured S3-backed staging bucket.")
    return storage


def _pdf(number: str, heading: str, details: list[str]) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle(number)
    pdf.setAuthor("Amaris Mathematics Academy")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(45, 785, "AMARIS MATHEMATICS ACADEMY")
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(45, 735, heading)
    pdf.setFont("Helvetica", 10)
    y = 695
    for detail in details:
        pdf.drawString(45, y, detail[:103])
        y -= 27
    pdf.setFont("Helvetica", 8)
    pdf.drawString(45, 52, "Invoice issued after server-verified PayFast payment. Not a Section 18A donation receipt.")
    pdf.save()
    return buffer.getvalue()


def _key(student_uuid, invoice_number):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", str(invoice_number)):
        raise StagingReceiptUnavailable("Invalid invoice reference.")
    return f"invoices/{student_uuid}/{invoice_number}.pdf"


def _save_once(storage, key, pdf):
    try:
        if storage.exists(key):
            with storage.open(key, "rb") as f:
                original = f.read()
            if not original.startswith(b"%PDF-"):
                raise StagingReceiptUnavailable("Invalid stored invoice PDF.")
            return original
        actual = storage.save(key, ContentFile(pdf))
        if actual != key:
            raise StagingReceiptUnavailable("Non-deterministic invoice storage key.")
        with storage.open(key, "rb") as f:
            stored = f.read()
        if stored != pdf:
            raise StagingReceiptUnavailable("Stored invoice checksum content mismatch.")
        return stored
    except Exception as exc:
        raise StagingReceiptUnavailable("Private invoice archive is unavailable.") from exc


def course_receipt(invoice: Invoice) -> bytes:
    if invoice.payment.status != Payment.Status.PAID or not invoice.payment.gateway_verified_at:
        raise StagingReceiptUnavailable("Unverified course payment.")
    key = _key(invoice.student.supabase_user_id, invoice.invoice_number)
    storage = private_receipt_storage()
    if storage.exists(key):
        return _save_once(storage, key, b"")
    pdf = _pdf(
        invoice.invoice_number, "PAID COURSE INVOICE",
        [
            f"Invoice: {invoice.invoice_number}",
            f"Payment: {invoice.payment.reference}",
            f"Student: {invoice.student.email}",
            f"Course: {invoice.course.title}",
            f"Amount: R{invoice.amount:.2f} {invoice.currency}",
            f"Issued: {timezone.localtime(invoice.issued_at).strftime('%d %B %Y')}",
        ],
    )
    return _save_once(storage, key, pdf)


def live_class_receipt(booking: LiveClassBooking) -> bytes:
    if (
        booking.status != LiveClassBooking.Status.CONFIRMED
        or not booking.gateway_verified_at
        or not booking.invoice_number
    ):
        raise StagingReceiptUnavailable("Unverified live-class payment.")
    key = _key(booking.student.supabase_user_id, booking.invoice_number)
    storage = private_receipt_storage()
    if storage.exists(key):
        return _save_once(storage, key, b"")
    pdf = _pdf(
        booking.invoice_number, "PAID LIVE CLASS INVOICE",
        [
            f"Invoice: {booking.invoice_number}",
            f"Booking: {booking.reference}",
            f"Student: {booking.student.email}",
            f"Programme: {booking.get_programme_display()}",
            f"Subject: {booking.get_subject_display()}",
            f"Level: {booking.level}",
            f"Topic: {booking.topic}",
            f"Amount: R{booking.amount:.2f} {booking.currency}",
        ],
    )
    return _save_once(storage, key, pdf)
