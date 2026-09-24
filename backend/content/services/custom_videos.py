from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from content.models import (
    CustomVideoInvoice,
    CustomVideoRequest,
    CustomVideoRequestFile,
    CustomVideoServiceSettings,
    StudentRecord,
    TutorAvailabilitySlot,
)

from .payments import (
    PAYFAST_LIVE_URL,
    PAYFAST_SANDBOX_URL,
    NotificationResult,
    PayFastVerificationGateway,
    PaymentSecurityError,
    _payfast_credentials,
    _payfast_mode,
    generate_payfast_signature,
)

SCHOOL_LEVELS = ("Grade 10", "Grade 11", "Grade 12")
ALLOWED_UPLOAD_EXTENSIONS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".heic",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".txt",
    ".csv",
    ".odt",
}
ALLOWED_UPLOAD_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/heic",
    "image/heif",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.oasis.opendocument.text",
    "text/plain",
    "text/csv",
    "application/csv",
    "application/octet-stream",
}
ZIP_EXTENSIONS = {".docx", ".xlsx", ".pptx", ".odt"}
OLE_EXTENSIONS = {".doc", ".xls", ".ppt"}


@dataclass(frozen=True)
class CustomVideoCheckoutSession:
    request_reference: str
    gateway_url: str
    fields: dict[str, str]


def get_custom_video_settings() -> CustomVideoServiceSettings | None:
    return CustomVideoServiceSettings.objects.filter(pk=1).first()


def _clean_text(value: object, *, minimum: int, maximum: int, label: str) -> str:
    cleaned = " ".join(str(value or "").split()).strip()
    if len(cleaned) < minimum or len(cleaned) > maximum:
        raise PaymentSecurityError(f"{label} must be between {minimum} and {maximum} characters.")
    return cleaned


def _validate_upload_signature(upload, extension: str) -> None:
    position = upload.tell() if hasattr(upload, "tell") else 0
    head = upload.read(1024)
    if hasattr(upload, "seek"):
        upload.seek(position)

    if extension == ".pdf" and not head.startswith(b"%PDF-"):
        raise PaymentSecurityError("The uploaded PDF does not contain a valid PDF signature.")
    if extension in {".jpg", ".jpeg"} and not head.startswith(b"\xff\xd8\xff"):
        raise PaymentSecurityError("The uploaded JPEG does not contain a valid JPEG signature.")
    if extension == ".png" and not head.startswith(b"\x89PNG\r\n\x1a\n"):
        raise PaymentSecurityError("The uploaded PNG does not contain a valid PNG signature.")
    if extension == ".heic":
        brand = head[4:16].lower()
        if not (len(head) >= 12 and head[4:8] == b"ftyp" and any(item in brand for item in (b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"))):
            raise PaymentSecurityError("The uploaded HEIC file does not contain a recognised HEIC signature.")
    if extension in ZIP_EXTENSIONS and not head.startswith(b"PK"):
        raise PaymentSecurityError("The uploaded Office/OpenDocument file is not a valid ZIP-based document.")
    if extension in OLE_EXTENSIONS and not head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        raise PaymentSecurityError("The uploaded legacy Office document does not contain a valid OLE signature.")
    if extension in {".txt", ".csv"} and b"\x00" in head:
        raise PaymentSecurityError("Text and CSV uploads may not contain binary NUL bytes.")


def validate_supporting_files(files: Iterable, settings_row: CustomVideoServiceSettings | None) -> list:
    uploads = list(files)
    max_files = settings_row.max_files if settings_row else 5
    max_file_size_mb = settings_row.max_file_size_mb if settings_row else 20
    if len(uploads) > max_files:
        raise PaymentSecurityError(f"Upload no more than {max_files} supporting files.")

    max_bytes = max_file_size_mb * 1024 * 1024
    for upload in uploads:
        name = Path(str(getattr(upload, "name", ""))).name
        extension = Path(name).suffix.lower()
        if extension not in ALLOWED_UPLOAD_EXTENSIONS:
            raise PaymentSecurityError(
                "Unsupported file type. Use PDF, JPG, PNG, HEIC, DOC/DOCX, XLS/XLSX, PPT/PPTX, TXT, CSV or ODT."
            )
        size = int(getattr(upload, "size", 0) or 0)
        if size <= 0:
            raise PaymentSecurityError(f"{name or 'Uploaded file'} is empty.")
        if size > max_bytes:
            raise PaymentSecurityError(f"{name} exceeds the {max_file_size_mb} MB per-file limit.")

        content_type = str(getattr(upload, "content_type", "") or "").lower().strip()
        if content_type and content_type not in ALLOWED_UPLOAD_MIME_TYPES and not content_type.startswith("text/"):
            raise PaymentSecurityError(f"{name} has an unsupported content type.")
        _validate_upload_signature(upload, extension)
    return uploads


def create_custom_video_request(
    *,
    student: StudentRecord,
    programme: str,
    subject: str,
    level: str,
    topic: str,
    idempotency_key: str,
    files: Iterable,
) -> CustomVideoRequest:
    key = idempotency_key.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", key):
        raise PaymentSecurityError("Invalid custom-video request idempotency key.")
    if not student.is_active:
        raise PaymentSecurityError("Inactive students cannot request custom videos.")

    programme_values = {value for value, _ in TutorAvailabilitySlot.Programme.choices}
    subject_values = {value for value, _ in TutorAvailabilitySlot.Subject.choices}
    if programme not in programme_values:
        raise PaymentSecurityError("Choose a valid curriculum stream.")
    if subject not in subject_values:
        raise PaymentSecurityError("Choose a valid subject.")

    clean_level = _clean_text(level, minimum=2, maximum=80, label="Grade or level")
    if programme in {TutorAvailabilitySlot.Programme.CAPS, TutorAvailabilitySlot.Programme.IEB}:
        if clean_level not in SCHOOL_LEVELS:
            raise PaymentSecurityError("CAPS and IEB custom-video requests are limited to Grade 10, 11 or 12.")

    clean_topic = _clean_text(topic, minimum=2, maximum=180, label="Topic")
    settings_row = get_custom_video_settings()
    uploads = validate_supporting_files(files, settings_row)

    existing = CustomVideoRequest.objects.filter(idempotency_key=key).first()
    if existing is not None:
        if (
            existing.student_id != student.pk
            or existing.programme != programme
            or existing.subject != subject
            or existing.level != clean_level
            or existing.topic != clean_topic
        ):
            raise PaymentSecurityError("This request key is already bound to another custom-video request.")
        return existing

    with transaction.atomic():
        video_request = CustomVideoRequest.objects.create(
            reference=f"CVR-{key}",
            idempotency_key=key,
            student=student,
            programme=programme,
            subject=subject,
            level=clean_level,
            topic=clean_topic,
            currency=(settings_row.currency if settings_row else "ZAR"),
        )
        saved: list[CustomVideoRequestFile] = []
        try:
            for upload in uploads:
                record = CustomVideoRequestFile.objects.create(
                    video_request=video_request,
                    file=upload,
                    original_name=Path(str(upload.name)).name[:255],
                    content_type=str(getattr(upload, "content_type", "") or "")[:120],
                    size_bytes=int(upload.size),
                )
                saved.append(record)
        except Exception:
            for record in saved:
                if record.file:
                    record.file.delete(save=False)
            raise
    return video_request


def _public_urls() -> tuple[str, str, str]:
    site_url = os.getenv(
        "PUBLIC_SITE_URL",
        "https://amaris-mathematics-academy.bethuelthipe.chatgpt.site",
    ).rstrip("/")
    api_url = os.getenv("PUBLIC_API_URL", "").rstrip("/")
    return_url = os.getenv(
        "PAYFAST_CUSTOM_VIDEO_RETURN_URL",
        f"{site_url}/request-your-own-video/confirmation",
    ).strip()
    cancel_url = os.getenv(
        "PAYFAST_CUSTOM_VIDEO_CANCEL_URL",
        f"{site_url}/payments/cancelled",
    ).strip()
    notify_url = os.getenv(
        "PAYFAST_NOTIFY_URL",
        f"{api_url}/api/v1/payfast/itn/" if api_url else "",
    ).strip()
    return return_url, cancel_url, notify_url


def create_custom_video_checkout(
    *,
    student: StudentRecord,
    video_request: CustomVideoRequest,
) -> CustomVideoCheckoutSession:
    settings_row = get_custom_video_settings()
    if settings_row is None or not settings_row.checkout_enabled:
        raise PaymentSecurityError(
            "Custom-video pricing is not configured yet. An administrator must set and enable the flat fee first."
        )

    with transaction.atomic():
        locked = CustomVideoRequest.objects.select_for_update().get(pk=video_request.pk)
        if locked.student_id != student.pk:
            raise PaymentSecurityError("This custom-video request does not belong to the authenticated student.")
        if locked.status in {CustomVideoRequest.Status.PAID, CustomVideoRequest.Status.IN_PROGRESS, CustomVideoRequest.Status.COMPLETED}:
            raise PaymentSecurityError("This custom-video request has already been paid.")
        if locked.status == CustomVideoRequest.Status.CANCELLED:
            locked.status = CustomVideoRequest.Status.DRAFT
        locked.amount = settings_row.flat_fee
        locked.currency = settings_row.currency
        locked.status = CustomVideoRequest.Status.PENDING_PAYMENT
        locked.provider_reference = ""
        locked.gateway_verified_at = None
        locked.paid_at = None
        locked.save(
            update_fields=(
                "amount",
                "currency",
                "status",
                "provider_reference",
                "gateway_verified_at",
                "paid_at",
                "updated_at",
            )
        )

    merchant_id, merchant_key, passphrase = _payfast_credentials()
    return_url, cancel_url, notify_url = _public_urls()
    fields = {
        "merchant_id": merchant_id,
        "merchant_key": merchant_key,
        "return_url": f"{return_url}?reference={locked.reference}",
        "cancel_url": f"{cancel_url}?reference={locked.reference}",
        "notify_url": notify_url,
        "name_first": student.first_name[:100],
        "name_last": student.last_name[:100],
        "email_address": student.email[:100],
        "m_payment_id": locked.reference,
        "amount": f"{locked.amount:.2f}",
        "item_name": "Amaris custom mathematics video request",
        "custom_str1": str(student.supabase_user_id),
        "custom_str2": locked.reference,
    }
    fields = {key: value for key, value in fields.items() if value != ""}
    fields["signature"] = generate_payfast_signature(fields, passphrase)
    return CustomVideoCheckoutSession(
        request_reference=locked.reference,
        gateway_url=PAYFAST_SANDBOX_URL if _payfast_mode() == "sandbox" else PAYFAST_LIVE_URL,
        fields=fields,
    )


def _decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def process_custom_video_notification(
    payload: Mapping[str, str],
    *,
    gateway: PayFastVerificationGateway,
) -> NotificationResult:
    reference = str(payload.get("m_payment_id", "")).strip()
    provider_reference = str(payload.get("pf_payment_id", "")).strip()
    gateway_status = str(payload.get("payment_status", "")).strip().upper()
    if not reference or not provider_reference or not gateway_status:
        return NotificationResult(False, "pending_payment", reason="missing_required_fields")

    try:
        video_request = CustomVideoRequest.objects.select_related("student").get(reference=reference)
    except CustomVideoRequest.DoesNotExist:
        return NotificationResult(False, "pending_payment", reason="unknown_custom_video_request")

    paid_statuses = {
        CustomVideoRequest.Status.PAID,
        CustomVideoRequest.Status.IN_PROGRESS,
        CustomVideoRequest.Status.COMPLETED,
    }
    if video_request.status in paid_statuses:
        if video_request.provider_reference == provider_reference:
            return NotificationResult(True, video_request.status, reason="duplicate_callback", duplicate=True)
        return NotificationResult(False, video_request.status, reason="provider_reference_replay", duplicate=True)

    try:
        verified = gateway.verify_notification(payload)
    except TimeoutError:
        return NotificationResult(False, video_request.status, reason="verification_timeout", retryable=True)
    except (ConnectionError, OSError):
        return NotificationResult(False, video_request.status, reason="verification_network_failure", retryable=True)
    if not verified:
        return NotificationResult(False, video_request.status, reason="invalid_callback")

    if video_request.provider_reference and video_request.provider_reference != provider_reference:
        return NotificationResult(False, video_request.status, reason="provider_reference_replay")
    if CustomVideoRequest.objects.filter(provider_reference=provider_reference).exclude(pk=video_request.pk).exists():
        return NotificationResult(False, video_request.status, reason="provider_reference_replay")

    amount = _decimal(payload.get("amount_gross"))
    if video_request.amount is None or amount is None or amount != video_request.amount:
        return NotificationResult(False, video_request.status, reason="tampered_amount")
    if str(payload.get("custom_str1", "")).strip() != str(video_request.student.supabase_user_id):
        return NotificationResult(False, video_request.status, reason="wrong_student")
    if str(payload.get("custom_str2", "")).strip() != video_request.reference:
        return NotificationResult(False, video_request.status, reason="wrong_service")

    completed = False
    with transaction.atomic():
        video_request = CustomVideoRequest.objects.select_for_update().select_related("student").get(pk=video_request.pk)
        video_request.provider_reference = provider_reference
        video_request.gateway_verified_at = timezone.now()

        if gateway_status == "COMPLETE":
            video_request.status = CustomVideoRequest.Status.PAID
            video_request.paid_at = timezone.now()
            if not video_request.invoice_number:
                video_request.invoice_number = (
                    f"INV-VIDEO-{video_request.paid_at:%Y%m%d}-{str(video_request.pk).replace('-', '')[:10].upper()}"
                )
            CustomVideoInvoice.objects.get_or_create(
                video_request=video_request,
                defaults={
                    "invoice_number": video_request.invoice_number,
                    "amount": video_request.amount,
                    "currency": video_request.currency,
                    "issued_at": video_request.paid_at,
                },
            )
            completed = True
        elif gateway_status in {"FAILED", "CANCELLED"}:
            video_request.status = CustomVideoRequest.Status.CANCELLED

        video_request.save(
            update_fields=(
                "provider_reference",
                "gateway_verified_at",
                "status",
                "paid_at",
                "invoice_number",
                "updated_at",
            )
        )

        if completed:
            def queue_notification() -> None:
                from content.tasks import deliver_custom_video_notifications

                deliver_custom_video_notifications.delay(str(video_request.pk))

            transaction.on_commit(queue_notification)

    return NotificationResult(True, video_request.status)


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_custom_video_invoice_pdf(video_request: CustomVideoRequest) -> bytes:
    if video_request.amount is None or not video_request.invoice_number:
        raise ValueError("A paid custom-video request must have an amount and invoice number.")

    lines = [
        "AMARIS MATHEMATICS ACADEMY",
        "Custom Video Request Invoice",
        "",
        f"Invoice: {video_request.invoice_number}",
        f"Request: {video_request.reference}",
        f"Student: {video_request.student.first_name} {video_request.student.last_name}".strip(),
        f"Email: {video_request.student.email}",
        f"Curriculum: {video_request.get_programme_display()}",
        f"Subject: {video_request.get_subject_display()}",
        f"Grade / level: {video_request.level}",
        f"Topic: {video_request.topic}",
        f"Amount: {video_request.currency} {video_request.amount:.2f}",
        f"Issued: {(video_request.paid_at or timezone.now()):%Y-%m-%d %H:%M %Z}",
        "",
        "Payment verified by the Amaris server before this invoice was issued.",
    ]
    commands = ["BT", "/F1 12 Tf", "50 790 Td"]
    for index, line in enumerate(lines):
        if index:
            commands.append("0 -20 Td")
        commands.append(f"({_pdf_escape(line)}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", errors="replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


def ensure_invoice_pdf(invoice: CustomVideoInvoice) -> CustomVideoInvoice:
    if invoice.pdf:
        return invoice
    payload = build_custom_video_invoice_pdf(invoice.video_request)
    invoice.pdf.save(
        f"{invoice.invoice_number}.pdf",
        ContentFile(payload),
        save=True,
    )
    return invoice
