"""Private, student-owned invoice PDFs stored in the student Supabase bucket."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import overload

from django.core.files.base import ContentFile
from django.core.files.storage import Storage, storages
from django.utils import timezone

from content.models import LiveClassBooking, VideoRequest
from content.payment_models import Invoice
from content.services.course_invoice_archive import (
    InvoiceArchiveError as InvoiceArchiveError,
)
from content.services.course_invoice_archive import (
    archive_invoice_pdf as archive_course_invoice_pdf,
)
from content.services.course_invoice_archive import build_invoice_pdf
from content.services.course_invoice_archive import (
    invoice_storage_path as invoice_storage_path,
)
from content.services.course_invoice_archive import (
    mark_invoice_archive_failure as mark_invoice_archive_failure,
)
from content.services.invoice_document import InvoiceDocument, InvoiceLine, render_document


def student_invoice_key(student_id: object, invoice_number: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", invoice_number):
        raise ValueError("Invalid invoice number.")
    return f"invoices/{student_id}/{invoice_number}.pdf"


def _invoice_identity(invoice: LiveClassBooking | VideoRequest) -> tuple[str, str]:
    if isinstance(invoice, LiveClassBooking) and invoice.status != LiveClassBooking.Status.CONFIRMED:
        raise ValueError("Only verified, confirmed bookings receive invoices.")
    if invoice.gateway_verified_at is None or not invoice.invoice_number:
        raise ValueError("Only server-verified payments receive invoices.")
    return invoice.invoice_number, invoice.student.email


def render_invoice_pdf(invoice: Invoice | LiveClassBooking | VideoRequest) -> bytes:
    if isinstance(invoice, Invoice):
        return build_invoice_pdf(invoice)
    number, email = _invoice_identity(invoice)
    if invoice.gateway_verified_at is None:
        raise ValueError("Only server-verified payments receive invoices.")
    if isinstance(invoice, LiveClassBooking):
        line = InvoiceLine(
            description=(
                f"{invoice.get_programme_display()} {invoice.get_subject_display()} - {invoice.level} live class"
            ),
            details=(
                f"Topic: {invoice.topic}",
                f"Tutor: {invoice.slot.tutor_display_name}",
                f"Date: {timezone.localtime(invoice.slot.starts_at):%d %B %Y at %H:%M} SAST",
                f"Duration: {invoice.slot.duration_hours} hour(s)",
            ),
            quantity=Decimal(invoice.slot.duration_hours),
            unit_price=Decimal("250.00"),
        )
    else:
        line = InvoiceLine(
            description=invoice.get_request_type_display(),
            details=(
                f"Subject: {invoice.get_programme_display()} / {invoice.get_subject_display()} / {invoice.level}",
                f"Topic: {invoice.topic}",
                f"Ticket: {invoice.ticket_number}",
            ),
            quantity=Decimal("1"),
            unit_price=invoice.amount,
        )
    return render_document(
        InvoiceDocument(
            number=number,
            issue_date=timezone.localtime(invoice.paid_at or invoice.gateway_verified_at).strftime("%d %B %Y"),
            student_name=f"{invoice.student.first_name} {invoice.student.last_name}".strip() or email,
            student_email=email,
            reference=invoice.reference,
            currency=invoice.currency,
            lines=(line,),
            total=invoice.amount,
        )
    )


@overload
def archive_invoice_pdf(invoice: int, *, storage: Storage | None = None) -> str: ...


@overload
def archive_invoice_pdf(
    invoice: Invoice | LiveClassBooking | VideoRequest,
    *,
    storage: Storage | None = None,
) -> bytes: ...


def archive_invoice_pdf(
    invoice: int | Invoice | LiveClassBooking | VideoRequest,
    *,
    storage: Storage | None = None,
) -> str | bytes:
    """Write the PDF to the private student bucket before delivery is marked sent."""
    if isinstance(invoice, int):
        return archive_course_invoice_pdf(invoice, storage=storage)
    if isinstance(invoice, Invoice):
        course_storage = storage or storages["student_private"]
        try:
            path = archive_course_invoice_pdf(invoice.pk, storage=course_storage)
            with course_storage.open(path, "rb") as archived:
                return archived.read()
        except Exception as exc:
            raise OSError("Student invoice archive is unavailable.") from exc
    document = render_invoice_pdf(invoice)
    invoice_number, _ = _invoice_identity(invoice)
    key = student_invoice_key(invoice.student.supabase_user_id, invoice_number)
    private_storage = storage or storages["student_private"]
    try:
        # Booking recipients share one canonical private PDF; never generate an
        # alternative object key for the same verified invoice on retries.
        if private_storage.exists(key):
            with private_storage.open(key, "rb") as archived:
                existing = archived.read()
            if not existing.startswith(b"%PDF-"):
                raise OSError("Previously archived booking invoice is not a PDF.")
            return existing
        saved = private_storage.save(key, ContentFile(document))
        if saved != key:
            raise OSError("Student invoice archive did not use the expected object key.")
    except Exception as exc:
        raise OSError("Student invoice archive is unavailable.") from exc
    return document
