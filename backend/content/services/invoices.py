"""Private, student-owned invoice PDFs stored in the student Supabase bucket."""

from __future__ import annotations

import io
import re
import textwrap

from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from content.models import LiveClassBooking, SiteSettings
from content.payment_models import Invoice


def student_invoice_key(student_id: object, invoice_number: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", invoice_number):
        raise ValueError("Invalid invoice number.")
    return f"invoices/{student_id}/{invoice_number}.pdf"


def _invoice_details(invoice: Invoice | LiveClassBooking) -> tuple[str, str, list[str]]:
    if isinstance(invoice, LiveClassBooking):
        if invoice.status != LiveClassBooking.Status.CONFIRMED or not invoice.invoice_number:
            raise ValueError("Only verified, confirmed bookings receive invoices.")
        starts_at = timezone.localtime(invoice.slot.starts_at).strftime("%d %B %Y at %H:%M SAST")
        return (
            invoice.invoice_number,
            invoice.student.email,
            [
                f"Student: {invoice.student.first_name} {invoice.student.last_name}",
                f"Booking: {invoice.reference}",
                f"Class: {invoice.get_programme_display()} / {invoice.get_subject_display()} / {invoice.level}",
                f"Topic: {invoice.topic}",
                f"Tutor: {invoice.slot.tutor_display_name}",
                f"Date: {starts_at}",
                f"Amount paid: R{invoice.amount:.2f} {invoice.currency}",
            ],
        )
    return (
        invoice.invoice_number,
        invoice.student.email,
        [
            f"Student: {invoice.student.first_name} {invoice.student.last_name}",
            f"Payment: {invoice.payment.reference}",
            f"Course: {invoice.course.title}",
            f"Date: {timezone.localtime(invoice.issued_at):%d %B %Y}",
            f"Amount paid: R{invoice.amount:.2f} {invoice.currency}",
        ],
    )


def render_invoice_pdf(invoice: Invoice | LiveClassBooking) -> bytes:
    invoice_number, student_email, details = _invoice_details(invoice)
    site = SiteSettings.objects.first()
    name = site.site_name if site else "Amaris Mathematics Academy"
    contact = site.email if site else "bethuelmoukangwe8@gmail.com"
    phone = site.phone if site else "071 415 6665"
    address = site.address if site else "Pretoria, Gauteng, South Africa"
    output = io.BytesIO()
    page = canvas.Canvas(output, pagesize=A4)
    page.setTitle(f"Invoice {invoice_number}")
    width, height = A4
    page.setFillColor(colors.HexColor("#07152d"))
    page.rect(0, height - 122, width, 122, fill=1, stroke=0)
    heading_x = 52
    if site and site.logo:
        try:
            with site.logo.open("rb") as logo:
                page.drawImage(ImageReader(io.BytesIO(logo.read())), 52, height - 100, 72, 72, mask="auto")
            heading_x = 140
        except (OSError, ValueError):
            pass
    page.setFillColor(colors.white)
    page.setFont("Helvetica-Bold", 15)
    page.drawString(heading_x, height - 60, name[:48])
    page.setFont("Helvetica", 9)
    page.drawString(heading_x, height - 79, f"{contact}  |  {phone}"[:75])
    page.setFillColor(colors.HexColor("#07152d"))
    page.setFont("Helvetica-Bold", 21)
    page.drawString(52, height - 170, "PAID INVOICE")
    page.setFont("Helvetica", 10)
    page.drawString(52, height - 194, f"Invoice number: {invoice_number}")
    page.drawString(52, height - 213, f"Issued to: {student_email}"[:100])
    y = height - 255
    for detail in details:
        for line in textwrap.wrap(detail, width=91):
            page.drawString(52, y, line)
            y -= 18
        y -= 7
    page.setStrokeColor(colors.HexColor("#dce4ef"))
    page.line(52, y - 4, width - 52, y - 4)
    page.setFont("Helvetica", 9)
    page.drawString(52, y - 25, "Payment verified through PayFast. Keep this invoice for your records.")
    for index, line in enumerate(textwrap.wrap(address, width=105)[:3]):
        page.drawString(52, 60 - index * 12, line)
    page.save()
    return output.getvalue()


def archive_invoice_pdf(invoice: Invoice | LiveClassBooking) -> bytes:
    """Write the PDF to the private student bucket before delivery is marked sent."""
    document = render_invoice_pdf(invoice)
    invoice_number, _, _ = _invoice_details(invoice)
    key = student_invoice_key(invoice.student.supabase_user_id, invoice_number)
    try:
        saved = storages["student_private"].save(key, ContentFile(document))
    except Exception as exc:
        raise OSError("Student invoice archive is unavailable.") from exc
    if saved != key:
        raise OSError("Student invoice archive did not use the expected object key.")
    return document
