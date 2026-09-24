from __future__ import annotations

import os
import re
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.db import IntegrityError, transaction
from django.utils import timezone

from content.models import (
    CustomVideoInvoice,
    CustomVideoRequest,
    CustomVideoRequestAttachment,
    CustomVideoSettings,
    StudentRecord,
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

CUSTOM_VIDEO_REFERENCE_PREFIX = "CVR-"
CUSTOM_VIDEO_CALLBACK_WINDOW = timedelta(days=7)

ALLOWED_SUPPORT_EXTENSIONS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".heic",
    ".heif",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".txt",
}

EXPECTED_CONTENT_TYPES = {
    ".pdf": {"application/pdf"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".heic": {"image/heic", "image/heif"},
    ".heif": {"image/heif", "image/heic"},
    ".doc": {"application/msword", "application/octet-stream"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
    },
    ".ppt": {"application/vnd.ms-powerpoint", "application/octet-stream"},
    ".pptx": {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/octet-stream",
    },
    ".xls": {"application/vnd.ms-excel", "application/octet-stream"},
    ".xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",
    },
    ".txt": {"text/plain"},
}

ZIP_OFFICE_EXTENSIONS = {".docx", ".pptx", ".xlsx"}
OLE_OFFICE_EXTENSIONS = {".doc", ".ppt", ".xls"}
HEIF_BRANDS = (b"ftypheic", b"ftypheix", b"ftyphevc", b"ftyphevx", b"ftypmif1", b"ftypmsf1")


class CustomVideoValidationError(ValueError):
    pass


@dataclass(frozen=True)
class CustomVideoCheckoutSession:
    request_reference: str
    gateway_url: str
    fields: dict[str, str]


def get_custom_video_settings() -> CustomVideoSettings | None:
    return CustomVideoSettings.objects.first()


def _file_header(uploaded_file, length: int = 32) -> bytes:
    position = uploaded_file.tell() if hasattr(uploaded_file, "tell") else 0
    header = uploaded_file.read(length)
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(position)
    return bytes(header)


def _signature_matches(extension: str, header: bytes) -> bool:
    if extension == ".pdf":
        return header.startswith(b"%PDF-")
    if extension in {".jpg", ".jpeg"}:
        return header.startswith(b"\xff\xd8\xff")
    if extension == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if extension in {".heic", ".heif"}:
        return any(brand in header for brand in HEIF_BRANDS)
    if extension in ZIP_OFFICE_EXTENSIONS:
        return header.startswith(b"PK\x03\x04")
    if extension in OLE_OFFICE_EXTENSIONS:
        return header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    if extension == ".txt":
        return b"\x00" not in header
    return False


def validate_supporting_files(
    files: Iterable,
    *,
    settings: CustomVideoSettings,
) -> list:
    uploads = list(files)
    if not uploads:
        raise CustomVideoValidationError("Upload at least one supporting file.")
    if len(uploads) > settings.max_files:
        raise CustomVideoValidationError(
            f"Upload no more than {settings.max_files} supporting files."
        )

    max_bytes = int(settings.max_file_size_mb) * 1024 * 1024
    for uploaded_file in uploads:
        name = Path(str(getattr(uploaded_file, "name", ""))).name
        extension = Path(name).suffix.lower()
        size = int(getattr(uploaded_file, "size", 0) or 0)
        content_type = str(getattr(uploaded_file, "content_type", "") or "").lower()

        if extension not in ALLOWED_SUPPORT_EXTENSIONS:
            raise CustomVideoValidationError(
                f"{name or 'A file'} has an unsupported file type."
            )
        if size <= 0:
            raise CustomVideoValidationError(f"{name} is empty.")
        if size > max_bytes:
            raise CustomVideoValidationError(
                f"{name} is larger than the {settings.max_file_size_mb} MB per-file limit."
            )

        expected_types = EXPECTED_CONTENT_TYPES.get(extension, set())
        if content_type and content_type not in expected_types:
            raise CustomVideoValidationError(
                f"{name} does not match an allowed content type."
            )
        if not _signature_matches(extension, _file_header(uploaded_file)):
            raise CustomVideoValidationError(
                f"{name} does not contain the expected file signature."
            )
    return uploads


def create_custom_video_request(
    *,
    student: StudentRecord,
    curriculum: str,
    subject: str,
    grade: str,
    topic: str,
    idempotency_key: str,
    files: Iterable,
) -> CustomVideoRequest:
    settings = get_custom_video_settings()
    if settings is None or not settings.enabled:
        raise CustomVideoValidationError(
            "Custom-video requests are not currently accepting submissions."
        )
    if settings.flat_fee is None:
        raise CustomVideoValidationError(
            "Custom-video pricing has not been configured by the academy."
        )
    if not student.is_active:
        raise CustomVideoValidationError("Inactive students cannot request custom videos.")

    key = idempotency_key.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", key):
        raise CustomVideoValidationError("Invalid request idempotency key.")

    cleaned_topic = " ".join(topic.split()).strip()
    if len(cleaned_topic) < 2 or len(cleaned_topic) > 220:
        raise CustomVideoValidationError("Enter a topic between 2 and 220 characters.")

    allowed_curricula = {value for value, _label in CustomVideoRequest._meta.get_field("curriculum").choices}
    allowed_subjects = {value for value, _label in CustomVideoRequest._meta.get_field("subject").choices}
    allowed_grades = {value for value, _label in CustomVideoRequest.Grade.choices}
    if curriculum not in allowed_curricula:
        raise CustomVideoValidationError("Choose a supported curriculum.")
    if subject not in allowed_subjects:
        raise CustomVideoValidationError("Choose a supported subject.")
    if grade not in allowed_grades:
        raise CustomVideoValidationError("Choose Grade 10, 11 or 12.")

    uploads = validate_supporting_files(files, settings=settings)

    existing = CustomVideoRequest.objects.filter(idempotency_key=key).first()
    if existing is not None:
        same_request = (
            existing.student_id == student.pk
            and existing.curriculum == curriculum
            and existing.subject == subject
            and existing.grade == grade
            and existing.topic == cleaned_topic
        )
        if not same_request:
            raise CustomVideoValidationError(
                "This request key is already bound to another custom-video request."
            )
        return existing

    request_record = None
    created_attachments: list[CustomVideoRequestAttachment] = []
    try:
        with transaction.atomic():
            request_record = CustomVideoRequest.objects.create(
                reference=f"{CUSTOM_VIDEO_REFERENCE_PREFIX}{uuid.uuid4().hex[:20].upper()}",
                idempotency_key=key,
                student=student,
                curriculum=curriculum,
                subject=subject,
                grade=grade,
                topic=cleaned_topic,
                currency=settings.currency,
            )
            for uploaded_file in uploads:
                attachment = CustomVideoRequestAttachment(
                    request=request_record,
                    original_name=Path(str(uploaded_file.name)).name[:255],
                    content_type=str(getattr(uploaded_file, "content_type", "") or "")[:120],
                    size_bytes=int(uploaded_file.size),
                )
                attachment.file.save(
                    Path(str(uploaded_file.name)).name,
                    uploaded_file,
                    save=False,
                )
                attachment.save()
                created_attachments.append(attachment)
        return request_record
    except Exception:
        for attachment in created_attachments:
            if attachment.file.name:
                attachment.file.storage.delete(attachment.file.name)
        raise


def _public_urls() -> tuple[str, str, str]:
    site_url = os.getenv(
        "PUBLIC_SITE_URL",
        "https://amaris-mathematics-academy-live-students.onrender.com",
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
    request_record: CustomVideoRequest,
) -> CustomVideoCheckoutSession:
    if request_record.student_id != student.pk:
        raise PaymentSecurityError("Custom-video request not found.")
    if request_record.status != CustomVideoRequest.Status.PENDING_PAYMENT:
        raise PaymentSecurityError("This custom-video request is not awaiting payment.")
    if not request_record.attachments.exists():
        raise PaymentSecurityError("Upload supporting files before payment.")

    settings = get_custom_video_settings()
    if settings is None or not settings.enabled or settings.flat_fee is None:
        raise PaymentSecurityError("Custom-video pricing is not currently available.")

    with transaction.atomic():
        locked = CustomVideoRequest.objects.select_for_update().get(pk=request_record.pk)
        if locked.status != CustomVideoRequest.Status.PENDING_PAYMENT:
            raise PaymentSecurityError("This custom-video request is not awaiting payment.")
        if locked.amount is None:
            locked.amount = settings.flat_fee
            locked.currency = settings.currency
            locked.save(update_fields=("amount", "currency", "updated_at"))
        amount = locked.amount

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
        "amount": f"{amount:.2f}",
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
        request_record = CustomVideoRequest.objects.select_related("student").get(
            reference=reference
        )
    except CustomVideoRequest.DoesNotExist:
        return NotificationResult(False, "pending_payment", reason="unknown_custom_video_request")

    if request_record.status in {
        CustomVideoRequest.Status.PAID,
        CustomVideoRequest.Status.IN_PROGRESS,
        CustomVideoRequest.Status.DELIVERED,
    }:
        if request_record.provider_reference == provider_reference:
            return NotificationResult(
                True,
                request_record.status,
                reason="duplicate_callback",
                duplicate=True,
            )
        return NotificationResult(
            False,
            request_record.status,
            reason="provider_reference_replay",
            duplicate=True,
        )

    if timezone.now() - request_record.created_at > CUSTOM_VIDEO_CALLBACK_WINDOW:
        return NotificationResult(
            False,
            request_record.status,
            reason="callback_window_expired",
        )

    try:
        verified = gateway.verify_notification(payload)
    except TimeoutError:
        return NotificationResult(
            False,
            request_record.status,
            reason="verification_timeout",
            retryable=True,
        )
    except (ConnectionError, OSError):
        return NotificationResult(
            False,
            request_record.status,
            reason="verification_network_failure",
            retryable=True,
        )
    if not verified:
        return NotificationResult(
            False,
            request_record.status,
            reason="invalid_callback",
        )

    if request_record.amount is None:
        return NotificationResult(
            False,
            request_record.status,
            reason="price_not_set",
        )
    amount = _decimal(payload.get("amount_gross"))
    if amount is None or amount != request_record.amount:
        return NotificationResult(
            False,
            request_record.status,
            reason="tampered_amount",
        )
    if str(payload.get("custom_str1", "")).strip() != str(
        request_record.student.supabase_user_id
    ):
        return NotificationResult(
            False,
            request_record.status,
            reason="wrong_student",
        )
    if str(payload.get("custom_str2", "")).strip() != request_record.reference:
        return NotificationResult(
            False,
            request_record.status,
            reason="wrong_service",
        )
    if (
        CustomVideoRequest.objects.filter(provider_reference=provider_reference)
        .exclude(pk=request_record.pk)
        .exists()
    ):
        return NotificationResult(
            False,
            request_record.status,
            reason="provider_reference_replay",
        )

    with transaction.atomic():
        request_record = CustomVideoRequest.objects.select_for_update().select_related(
            "student"
        ).get(pk=request_record.pk)
        request_record.provider_reference = provider_reference
        request_record.gateway_verified_at = timezone.now()

        if gateway_status == "COMPLETE":
            request_record.status = CustomVideoRequest.Status.PAID
            request_record.paid_at = timezone.now()
            invoice_number = (
                f"INV-VIDEO-{request_record.paid_at:%Y%m%d}-"
                f"{str(request_record.pk).replace('-', '')[:10].upper()}"
            )
            CustomVideoInvoice.objects.get_or_create(
                request=request_record,
                defaults={
                    "invoice_number": invoice_number,
                    "amount": request_record.amount,
                    "currency": request_record.currency,
                    "issued_at": request_record.paid_at,
                },
            )
        elif gateway_status in {"FAILED", "CANCELLED"}:
            request_record.status = CustomVideoRequest.Status.CANCELLED

        request_record.save(
            update_fields=(
                "provider_reference",
                "gateway_verified_at",
                "status",
                "paid_at",
                "updated_at",
            )
        )

    return NotificationResult(True, request_record.status)
