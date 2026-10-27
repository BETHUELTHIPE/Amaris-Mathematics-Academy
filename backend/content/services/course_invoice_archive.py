from __future__ import annotations

import hashlib
import re
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.files.storage import Storage, storages
from django.utils import timezone

from content.models import Payment
from content.services.approved_invoice_letterhead import require_approved_invoice_letterhead
from content.payment_models import Invoice
from content.services.invoice_document import InvoiceDocument, InvoiceLine, render_document


class InvoiceArchiveError(RuntimeError):
    """Raised when a verified invoice cannot be archived safely."""


def invoice_storage_path(invoice: Invoice) -> str:
    safe_number = re.sub(r"[^A-Za-z0-9._-]+", "-", invoice.invoice_number).strip("-") or "invoice"
    return f"{invoice.student.supabase_user_id}/invoices/{safe_number}.pdf"


def build_invoice_pdf(invoice: Invoice) -> bytes:
    """Use the same approved letterhead as booking and video invoices."""
    invoice = _ensure_invoice_relations(invoice)
    return render_document(
        InvoiceDocument(
            number=invoice.invoice_number,
            issue_date=timezone.localtime(invoice.issued_at).strftime("%d %B %Y"),
            student_name=f"{invoice.student.first_name} {invoice.student.last_name}".strip() or invoice.student.email,
            student_email=invoice.student.email,
            reference=invoice.payment.reference,
            currency=invoice.currency,
            lines=(
                InvoiceLine(
                    description=invoice.course.title,
                    details=("Mathematics course enrolment",),
                    quantity=Decimal("1"),
                    unit_price=invoice.amount,
                ),
            ),
            total=invoice.amount,
        )
    )


def archive_invoice_pdf(invoice_id: int, *, storage: Storage | None = None) -> str:
    """Generate and persist one paid invoice under the student's private UUID folder."""

    invoice = Invoice.objects.select_related("payment", "student", "course").get(pk=invoice_id)
    if invoice.payment.status != Payment.Status.PAID or invoice.payment.gateway_verified_at is None:
        raise InvoiceArchiveError("Only server-verified paid invoices may be archived.")

    if storage is None:
        storage = storages["student_documents"]

    path = invoice_storage_path(invoice)

    if storage.exists(path):
        with storage.open(path, "rb") as existing:
            pdf_bytes = existing.read()
        require_approved_invoice_letterhead(pdf_bytes)
    else:
        pdf_bytes = build_invoice_pdf(invoice)
        require_approved_invoice_letterhead(pdf_bytes)
        saved_name = storage.save(path, ContentFile(pdf_bytes, name=path.rsplit("/", 1)[-1]))
        if saved_name != path:
            try:
                storage.delete(saved_name)
            except Exception:
                pass
            raise InvoiceArchiveError("Invoice storage returned a non-deterministic object path.")

    Invoice.objects.filter(pk=invoice.pk).update(
        pdf_storage_path=path,
        pdf_sha256=hashlib.sha256(pdf_bytes).hexdigest(),
        pdf_generated_at=invoice.pdf_generated_at or timezone.now(),
        pdf_last_error_code="",
    )
    return path


def mark_invoice_archive_failure(invoice_id: int, exc: BaseException) -> None:
    Invoice.objects.filter(pk=invoice_id).update(
        pdf_last_error_code=exc.__class__.__name__[:120],
    )


def _ensure_invoice_relations(invoice: Invoice) -> Invoice:
    if all(hasattr(invoice, relation) for relation in ("payment", "student", "course")):
        return invoice
    return Invoice.objects.select_related("payment", "student", "course").get(pk=invoice.pk)
