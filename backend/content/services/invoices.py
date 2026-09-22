from __future__ import annotations

import hashlib
import re
import textwrap
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage, storages
from django.utils import timezone
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from content.models import Payment, SiteSettings
from content.payment_models import Invoice


class InvoiceArchiveError(RuntimeError):
    """Raised when a verified invoice cannot be archived safely."""


def invoice_storage_path(invoice: Invoice) -> str:
    safe_number = re.sub(r"[^A-Za-z0-9._-]+", "-", invoice.invoice_number).strip("-") or "invoice"
    return f"{invoice.student.supabase_user_id}/invoices/{safe_number}.pdf"


def build_invoice_pdf(invoice: Invoice) -> bytes:
    """Render one immutable paid invoice as a branded A4 PDF."""

    invoice = _ensure_invoice_relations(invoice)
    buffer = BytesIO()
    page_width, page_height = A4
    pdf = canvas.Canvas(buffer, pagesize=A4, pageCompression=1)
    pdf.setTitle(invoice.invoice_number)
    pdf.setAuthor("Amaris Mathematics Academy")
    pdf.setSubject(f"Paid invoice for {invoice.course.title}")

    navy = HexColor("#07152D")
    blue = HexColor("#1F5BBD")
    slate = HexColor("#60708A")
    line = HexColor("#DCE4EF")
    pale = HexColor("#F5F7FB")
    green = HexColor("#13715F")

    site = SiteSettings.objects.first()
    academy_name = site.site_name if site else "Amaris Mathematics Academy"
    phone = site.phone if site else "071 415 6665"
    email = site.email if site else "bethuelmoukangwe8@gmail.com"
    address = (
        " ".join((site.address or "").split())
        if site
        else "27 Tshivhase Street, Atteridgeville, Pretoria, Gauteng, 0008"
    )

    pdf.setFillColor(navy)
    pdf.rect(0, page_height - 118, page_width, 118, fill=1, stroke=0)

    logo_drawn = False
    if site and site.logo:
        try:
            with site.logo.open("rb") as logo_file:
                logo_data = logo_file.read()
            if logo_data:
                pdf.drawImage(
                    ImageReader(BytesIO(logo_data)),
                    42,
                    page_height - 94,
                    width=48,
                    height=48,
                    preserveAspectRatio=True,
                    mask="auto",
                )
                logo_drawn = True
        except Exception:
            logo_drawn = False

    title_x = 102 if logo_drawn else 42
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(title_x, page_height - 60, academy_name[:48])
    pdf.setFont("Helvetica", 8.5)
    pdf.drawString(title_x, page_height - 78, f"{phone}  |  {email}"[:88])
    pdf.drawString(title_x, page_height - 92, address[:100])

    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawRightString(page_width - 42, page_height - 63, "INVOICE")
    pdf.setFont("Helvetica", 9)
    pdf.drawRightString(page_width - 42, page_height - 82, "PAID · SERVER VERIFIED")

    top = page_height - 150
    pdf.setFillColor(blue)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(42, top, "BILLED TO")
    pdf.setFillColor(navy)
    pdf.setFont("Helvetica-Bold", 13)
    student_name = f"{invoice.student.first_name} {invoice.student.last_name}".strip() or invoice.student.email
    pdf.drawString(42, top - 22, student_name[:60])
    pdf.setFillColor(slate)
    pdf.setFont("Helvetica", 9.5)
    pdf.drawString(42, top - 39, invoice.student.email[:80])

    details_x = 330
    detail_rows = [
        ("Invoice number", invoice.invoice_number),
        ("Issue date", timezone.localtime(invoice.issued_at).strftime("%d %B %Y")),
        ("Payment reference", invoice.payment.reference),
        ("Currency", invoice.currency),
    ]
    y = top
    for label, value in detail_rows:
        pdf.setFillColor(slate)
        pdf.setFont("Helvetica", 8.5)
        pdf.drawString(details_x, y, label)
        pdf.setFillColor(navy)
        pdf.setFont("Helvetica-Bold", 8.5)
        pdf.drawRightString(page_width - 42, y, str(value)[:46])
        y -= 18

    table_top = top - 105
    pdf.setFillColor(navy)
    pdf.roundRect(42, table_top - 30, page_width - 84, 30, 7, fill=1, stroke=0)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(55, table_top - 19, "Description")
    pdf.drawCentredString(381, table_top - 19, "Qty")
    pdf.drawRightString(469, table_top - 19, "Unit price")
    pdf.drawRightString(page_width - 55, table_top - 19, "Amount")

    row_top = table_top - 30
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setStrokeColor(line)
    pdf.roundRect(42, row_top - 78, page_width - 84, 78, 7, fill=1, stroke=1)
    pdf.setFillColor(navy)
    pdf.setFont("Helvetica-Bold", 10.5)
    course_lines = textwrap.wrap(invoice.course.title, width=48)[:2] or ["Mathematics course"]
    desc_y = row_top - 25
    for course_line in course_lines:
        pdf.drawString(55, desc_y, course_line)
        desc_y -= 14
    pdf.setFillColor(slate)
    pdf.setFont("Helvetica", 8.5)
    pdf.drawString(55, row_top - 60, f"Verified payment: {invoice.payment.reference}"[:72])

    amount = f"R {invoice.amount:,.2f}"
    pdf.setFillColor(navy)
    pdf.setFont("Helvetica", 10)
    pdf.drawCentredString(381, row_top - 39, "1")
    pdf.drawRightString(469, row_top - 39, amount)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawRightString(page_width - 55, row_top - 39, amount)

    total_top = row_top - 105
    pdf.setFillColor(pale)
    pdf.roundRect(330, total_top - 92, page_width - 372, 92, 9, fill=1, stroke=0)
    pdf.setFillColor(slate)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(345, total_top - 24, "Subtotal")
    pdf.drawRightString(page_width - 55, total_top - 24, amount)
    pdf.drawString(345, total_top - 44, "Tax")
    pdf.drawRightString(page_width - 55, total_top - 44, "Included where applicable")
    pdf.setStrokeColor(line)
    pdf.line(345, total_top - 56, page_width - 55, total_top - 56)
    pdf.setFillColor(navy)
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(345, total_top - 78, "Total")
    pdf.drawRightString(page_width - 55, total_top - 78, amount)

    note_top = total_top - 125
    pdf.setFillColor(HexColor("#EDF9F2"))
    pdf.roundRect(42, note_top - 72, page_width - 84, 72, 9, fill=1, stroke=0)
    pdf.setFillColor(green)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(55, note_top - 21, "PAYMENT VERIFIED")
    pdf.setFillColor(navy)
    pdf.setFont("Helvetica", 8.8)
    note = (
        "This invoice was issued automatically after server-side payment verification. "
        "Course access is linked to the verified payment reference above."
    )
    for index, note_line in enumerate(textwrap.wrap(note, width=92)[:3]):
        pdf.drawString(55, note_top - 39 - (index * 12), note_line)

    pdf.setStrokeColor(line)
    pdf.line(42, 58, page_width - 42, 58)
    pdf.setFillColor(slate)
    pdf.setFont("Helvetica", 7.8)
    pdf.drawString(42, 41, f"Amaris Mathematics Academy · {invoice.invoice_number}")
    pdf.drawRightString(page_width - 42, 41, "Generated from a verified payment record")

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def archive_invoice_pdf(invoice_id: int, *, storage: Storage | None = None) -> str:
    """Generate and persist one paid invoice under the student's private UUID folder."""

    invoice = Invoice.objects.select_related("payment", "student", "course").get(pk=invoice_id)
    if invoice.payment.status != Payment.Status.PAID or invoice.payment.gateway_verified_at is None:
        raise InvoiceArchiveError("Only server-verified paid invoices may be archived.")

    if storage is None:
        if not getattr(settings, "SUPABASE_STORAGE_ENABLED", False):
            raise InvoiceArchiveError("Supabase Storage is not enabled for invoice archival.")
        storage = storages["student_documents"]

    pdf_bytes = build_invoice_pdf(invoice)
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    path = invoice_storage_path(invoice)

    if storage.exists(path):
        with storage.open(path, "rb") as existing:
            existing_digest = hashlib.sha256(existing.read()).hexdigest()
        if existing_digest != digest:
            storage.delete(path)

    if not storage.exists(path):
        saved_name = storage.save(path, ContentFile(pdf_bytes, name=path.rsplit("/", 1)[-1]))
        if saved_name != path:
            try:
                storage.delete(saved_name)
            except Exception:
                pass
            raise InvoiceArchiveError("Invoice storage returned a non-deterministic object path.")

    Invoice.objects.filter(pk=invoice.pk).update(
        pdf_storage_path=path,
        pdf_sha256=digest,
        pdf_generated_at=timezone.now(),
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
