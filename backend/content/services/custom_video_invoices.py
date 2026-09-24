from __future__ import annotations

from django.core.files.base import ContentFile

from content.models import CustomVideoInvoice, SiteSettings


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_custom_video_invoice_pdf(invoice: CustomVideoInvoice) -> bytes:
    request_record = invoice.request
    site = SiteSettings.objects.first()
    academy_name = site.site_name if site else "Amaris Mathematics Academy"
    academy_email = site.email if site else "bethuelmoukangwe8@gmail.com"
    academy_phone = site.phone if site else "071 415 6665"

    lines = [
        academy_name,
        f"{academy_email} | {academy_phone}",
        "",
        "CUSTOM VIDEO REQUEST INVOICE",
        f"Invoice: {invoice.invoice_number}",
        f"Request: {request_record.reference}",
        f"Student: {request_record.student.first_name} {request_record.student.last_name}",
        f"Email: {request_record.student.email}",
        f"Curriculum: {request_record.get_curriculum_display()}",
        f"Subject: {request_record.get_subject_display()}",
        f"Grade: {request_record.get_grade_display()}",
        f"Topic: {request_record.topic}",
        f"Amount: R{invoice.amount:.2f}",
        f"Currency: {invoice.currency}",
        f"Issued: {invoice.issued_at:%Y-%m-%d %H:%M}",
        "Payment status: Paid and verified by PayFast",
    ]

    commands = ["BT", "/F1 18 Tf", "72 790 Td"]
    for index, line in enumerate(lines):
        size = 18 if index == 0 else 11
        if index == 3:
            size = 15
        commands.append(f"/F1 {size} Tf")
        commands.append(f"({_pdf_escape(line)}) Tj")
        commands.append("0 -26 Td" if index in {0, 3} else "0 -19 Td")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", "replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def ensure_custom_video_invoice_pdf(invoice: CustomVideoInvoice) -> CustomVideoInvoice:
    if invoice.pdf_file.name:
        return invoice
    content = ContentFile(build_custom_video_invoice_pdf(invoice))
    invoice.pdf_file.save(f"{invoice.invoice_number}.pdf", content, save=True)
    return invoice
