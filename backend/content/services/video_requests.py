from __future__ import annotations

import hashlib
import io
import os
import re
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse

from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from PIL import Image, UnidentifiedImageError

from content.models import StudentRecord, VideoRequest, VideoRequestDocument

from .payments import (
    DEFAULT_PUBLIC_SITE_URL,
    PAYFAST_LIVE_URL,
    PAYFAST_SANDBOX_URL,
    NotificationResult,
    PayFastVerificationGateway,
    PaymentSecurityError,
    _payfast_credentials,
    _payfast_mode,
    build_payfast_notify_url,
    generate_payfast_signature,
)

VIDEO_REQUEST_PRICES: dict[str, Decimal] = {
    VideoRequest.RequestType.CHAPTER_TOPIC: Decimal("450.00"),
    VideoRequest.RequestType.PREVIOUS_ASSIGNMENT: Decimal("450.00"),
    VideoRequest.RequestType.PREVIOUS_EXAM: Decimal("1800.00"),
    VideoRequest.RequestType.COMPLETE_CONTENT: Decimal("1800.00"),
}
MAX_DOCUMENTS = 5
MAX_DOCUMENT_SIZE = 10 * 1024 * 1024
MAX_TOTAL_DOCUMENT_SIZE = 25 * 1024 * 1024
ALLOWED_DOCUMENT_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}
ACTIVE_QUEUE_STATUSES = (
    VideoRequest.Status.QUEUED,
    VideoRequest.Status.TUTOR_ASSIGNED,
    VideoRequest.Status.RECORDING,
    VideoRequest.Status.PROCESSING,
    VideoRequest.Status.REVIEW,
)


@dataclass(frozen=True)
class VideoRequestCheckoutSession:
    request_reference: str
    gateway_url: str
    fields: dict[str, str]


@dataclass(frozen=True)
class ValidatedDocument:
    original_name: str
    content_type: str
    data: bytes
    sha256: str
    extension: str


def _clean_text(value: object, *, maximum: int, minimum: int = 0) -> str:
    cleaned = " ".join(str(value or "").split()).strip()
    if len(cleaned) < minimum or len(cleaned) > maximum:
        raise PaymentSecurityError(f"Enter between {minimum} and {maximum} characters.")
    return cleaned


def _validate_document(upload) -> ValidatedDocument:
    original_name = Path(str(getattr(upload, "name", "document"))).name[:255]
    size = int(getattr(upload, "size", 0) or 0)
    if size <= 0 or size > MAX_DOCUMENT_SIZE:
        raise PaymentSecurityError("Each supporting document must be between 1 byte and 10 MB.")
    content_type = str(getattr(upload, "content_type", "") or "").lower()
    if content_type not in ALLOWED_DOCUMENT_TYPES:
        raise PaymentSecurityError("Supporting documents must be PDF, JPEG or PNG files.")
    data = upload.read(MAX_DOCUMENT_SIZE + 1)
    if len(data) != size or len(data) > MAX_DOCUMENT_SIZE:
        raise PaymentSecurityError("The supporting document could not be validated safely.")

    if content_type == "application/pdf":
        if not data.startswith(b"%PDF-"):
            raise PaymentSecurityError("The uploaded PDF is not valid.")
    else:
        try:
            with Image.open(io.BytesIO(data)) as image:
                image.verify()
                actual = (image.format or "").upper()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise PaymentSecurityError("The uploaded image is not valid.") from exc
        expected = "JPEG" if content_type == "image/jpeg" else "PNG"
        if actual != expected:
            raise PaymentSecurityError("The uploaded image type does not match its content.")

    return ValidatedDocument(
        original_name=original_name,
        content_type=content_type,
        data=data,
        sha256=hashlib.sha256(data).hexdigest(),
        extension=ALLOWED_DOCUMENT_TYPES[content_type],
    )


def validate_documents(documents: Iterable[object]) -> list[ValidatedDocument]:
    items = list(documents)
    if len(items) > MAX_DOCUMENTS:
        raise PaymentSecurityError(f"Upload no more than {MAX_DOCUMENTS} supporting documents.")
    validated = [_validate_document(upload) for upload in items]
    if sum(len(item.data) for item in validated) > MAX_TOTAL_DOCUMENT_SIZE:
        raise PaymentSecurityError("Supporting documents may not exceed 25 MB in total.")
    return validated


def video_request_document_key(request: VideoRequest, document: ValidatedDocument) -> str:
    token = uuid.uuid4().hex[:12]
    return (
        f"{request.student.supabase_user_id}/video-requests/{request.pk}/documents/"
        f"{document.sha256[:16]}-{token}{document.extension}"
    )


def _checkout_urls() -> tuple[str, str, str]:
    site_url = os.getenv("PUBLIC_SITE_URL", DEFAULT_PUBLIC_SITE_URL).rstrip("/")
    api_url = os.getenv("PUBLIC_API_URL", "").rstrip("/")
    return_url = os.getenv(
        "PAYFAST_VIDEO_REQUEST_RETURN_URL",
        f"{site_url}/request-a-video/confirmation",
    ).strip()
    cancel_url = os.getenv(
        "PAYFAST_VIDEO_REQUEST_CANCEL_URL",
        f"{site_url}/payments/cancelled",
    ).strip()
    notify_url = os.getenv("PAYFAST_NOTIFY_URL", build_payfast_notify_url(api_url)).strip()
    return return_url, cancel_url, notify_url


def _checkout_fields(request: VideoRequest) -> tuple[str, dict[str, str]]:
    merchant_id, merchant_key, passphrase = _payfast_credentials()
    return_url, cancel_url, notify_url = _checkout_urls()
    if _payfast_mode() == "live" and any(
        urlparse(url).scheme != "https" or not urlparse(url).netloc for url in (return_url, cancel_url, notify_url)
    ):
        raise PaymentSecurityError("Live PayFast video-request URLs must use HTTPS.")
    fields = {
        "merchant_id": merchant_id,
        "merchant_key": merchant_key,
        "return_url": f"{return_url}?reference={request.reference}",
        "cancel_url": f"{cancel_url}?reference={request.reference}",
        "notify_url": notify_url,
        "name_first": request.student.first_name[:100],
        "name_last": request.student.last_name[:100],
        "email_address": request.student.email[:100],
        "m_payment_id": request.reference,
        "amount": f"{request.amount:.2f}",
        "item_name": request.get_request_type_display()[:100],
        "custom_str1": str(request.student.supabase_user_id),
        "custom_str2": request.reference,
    }
    fields = {key: value for key, value in fields.items() if value != ""}
    fields["signature"] = generate_payfast_signature(fields, passphrase)
    gateway_url = PAYFAST_SANDBOX_URL if _payfast_mode() == "sandbox" else PAYFAST_LIVE_URL
    return gateway_url, fields


def create_video_request_checkout(
    *,
    student: StudentRecord,
    programme: str,
    subject: str,
    level: str,
    topic: str,
    request_type: str,
    instructions: str,
    explanation_style: str,
    preferred_duration_minutes: int,
    idempotency_key: str,
    documents: Iterable[object] = (),
) -> VideoRequestCheckoutSession:
    key = idempotency_key.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", key):
        raise PaymentSecurityError("Invalid video-request idempotency key.")
    if not student.is_active:
        raise PaymentSecurityError("Inactive students cannot request videos.")
    if programme not in TutorProgramme.values:
        raise PaymentSecurityError("Choose a supported programme.")
    if subject not in TutorSubject.values:
        raise PaymentSecurityError("Choose a supported subject.")
    if request_type not in VIDEO_REQUEST_PRICES:
        raise PaymentSecurityError("Choose a supported video package.")
    if not 15 <= preferred_duration_minutes <= 180:
        raise PaymentSecurityError("Preferred duration must be between 15 and 180 minutes.")

    cleaned_level = _clean_text(level, minimum=1, maximum=80)
    cleaned_topic = _clean_text(topic, minimum=2, maximum=180)
    cleaned_instructions = _clean_text(instructions, maximum=2000)
    cleaned_style = _clean_text(explanation_style, maximum=120)
    validated_documents = validate_documents(documents)
    amount = VIDEO_REQUEST_PRICES[request_type]
    reference = f"VRQ-{key}"
    storage = storages["student_private"]
    saved_paths: list[str] = []

    try:
        with transaction.atomic():
            existing = VideoRequest.objects.select_for_update().filter(idempotency_key=key).first()
            if existing is not None:
                same_request = (
                    existing.student_id == student.pk
                    and existing.programme == programme
                    and existing.subject == subject
                    and existing.level == cleaned_level
                    and existing.topic == cleaned_topic
                    and existing.request_type == request_type
                    and existing.instructions == cleaned_instructions
                    and existing.explanation_style == cleaned_style
                    and existing.preferred_duration_minutes == preferred_duration_minutes
                )
                if not same_request:
                    raise PaymentSecurityError("This request key is already bound to different video details.")
                if existing.status != VideoRequest.Status.PENDING_PAYMENT:
                    raise PaymentSecurityError("This video request checkout has already ended.")
                request = existing
            else:
                request = VideoRequest.objects.create(
                    reference=reference,
                    idempotency_key=key,
                    student=student,
                    programme=programme,
                    subject=subject,
                    level=cleaned_level,
                    topic=cleaned_topic,
                    request_type=request_type,
                    instructions=cleaned_instructions,
                    explanation_style=cleaned_style,
                    preferred_duration_minutes=preferred_duration_minutes,
                    amount=amount,
                )

            if validated_documents and not request.documents.exists():
                for document in validated_documents:
                    path = video_request_document_key(request, document)
                    saved = storage.save(path, ContentFile(document.data, name=Path(path).name))
                    if saved != path:
                        storage.delete(saved)
                        raise OSError("Private storage returned a non-deterministic document path.")
                    saved_paths.append(path)
                    VideoRequestDocument.objects.create(
                        request=request,
                        original_name=document.original_name,
                        storage_path=path,
                        content_type=document.content_type,
                        size_bytes=len(document.data),
                        sha256=document.sha256,
                    )
    except Exception:
        for path in saved_paths:
            try:
                storage.delete(path)
            except Exception:
                pass
        raise

    gateway_url, fields = _checkout_fields(request)
    return VideoRequestCheckoutSession(request_reference=request.reference, gateway_url=gateway_url, fields=fields)


class TutorProgramme:
    values = {"caps", "ieb", "tvet", "university"}


class TutorSubject:
    values = {"mathematics", "mathematical_literacy"}


def _decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def process_video_request_notification(
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
        request = VideoRequest.objects.select_related("student").get(reference=reference)
    except VideoRequest.DoesNotExist:
        return NotificationResult(False, "pending_payment", reason="unknown_video_request")

    if request.status in ACTIVE_QUEUE_STATUSES or request.status == VideoRequest.Status.READY:
        if request.provider_reference == provider_reference:
            return NotificationResult(True, request.status, reason="duplicate_callback", duplicate=True)
        return NotificationResult(False, request.status, reason="provider_reference_replay", duplicate=True)

    try:
        verified = gateway.verify_notification(payload)
    except TimeoutError:
        return NotificationResult(False, request.status, reason="verification_timeout", retryable=True)
    except (ConnectionError, OSError):
        return NotificationResult(False, request.status, reason="verification_network_failure", retryable=True)
    if not verified:
        return NotificationResult(False, request.status, reason="invalid_callback")
    if request.provider_reference and request.provider_reference != provider_reference:
        return NotificationResult(False, request.status, reason="provider_reference_replay")
    if VideoRequest.objects.filter(provider_reference=provider_reference).exclude(pk=request.pk).exists():
        return NotificationResult(False, request.status, reason="provider_reference_replay")
    if _decimal(payload.get("amount_gross")) != request.amount:
        return NotificationResult(False, request.status, reason="tampered_amount")
    if str(payload.get("custom_str1", "")).strip() != str(request.student.supabase_user_id):
        return NotificationResult(False, request.status, reason="wrong_student")
    if str(payload.get("custom_str2", "")).strip() != request.reference:
        return NotificationResult(False, request.status, reason="wrong_service")

    now = timezone.now()
    with transaction.atomic():
        request = VideoRequest.objects.select_for_update().select_related("student").get(pk=request.pk)
        if request.status in ACTIVE_QUEUE_STATUSES or request.status == VideoRequest.Status.READY:
            if request.provider_reference == provider_reference:
                return NotificationResult(True, request.status, reason="duplicate_callback", duplicate=True)
            return NotificationResult(False, request.status, reason="provider_reference_replay")
        request.provider_reference = provider_reference
        request.gateway_verified_at = now
        request.paid_at = now if gateway_status == "COMPLETE" else request.paid_at
        if gateway_status == "COMPLETE":
            if request.status != VideoRequest.Status.PENDING_PAYMENT or request.payment_expires_at <= now:
                request.status = VideoRequest.Status.PAYMENT_REVIEW
            else:
                request.status = VideoRequest.Status.QUEUED
                request.queue_entered_at = now
                request.ticket_number = f"AMARIS-VID-{now:%Y}-{request.pk.hex[:8].upper()}"
                request.invoice_number = f"INV-VID-{now:%Y%m%d}-{request.pk.hex[:10].upper()}"
        elif gateway_status in {"FAILED", "CANCELLED"}:
            if request.status == VideoRequest.Status.PENDING_PAYMENT:
                request.status = VideoRequest.Status.CANCELLED
        request.save(
            update_fields=(
                "provider_reference",
                "gateway_verified_at",
                "paid_at",
                "status",
                "queue_entered_at",
                "ticket_number",
                "invoice_number",
                "updated_at",
            )
        )
    return NotificationResult(
        True,
        request.status,
        reason="payment_requires_manual_resolution" if request.status == VideoRequest.Status.PAYMENT_REVIEW else "",
    )


def video_request_queue_position(request: VideoRequest) -> int | None:
    if request.status not in ACTIVE_QUEUE_STATUSES or request.queue_entered_at is None:
        return None
    active = VideoRequest.objects.filter(status__in=ACTIVE_QUEUE_STATUSES).exclude(pk=request.pk)
    in_progress = active.exclude(status=VideoRequest.Status.QUEUED).count()
    waiting = active.filter(status=VideoRequest.Status.QUEUED)
    if request.priority_paid_at:
        ahead = waiting.filter(
            priority_paid_at__isnull=False,
            priority_paid_at__lt=request.priority_paid_at,
        ).count()
    else:
        ahead = waiting.filter(
            Q(priority_paid_at__isnull=False)
            | Q(priority_paid_at__isnull=True, queue_entered_at__lt=request.queue_entered_at)
        ).count()
    return in_progress + ahead + 1


def video_request_eta(request: VideoRequest) -> tuple[str | None, str | None]:
    position = video_request_queue_position(request)
    if position is None:
        return None, None
    capacity = max(1, int(os.getenv("VIDEO_REQUEST_DAILY_CAPACITY", "2")))
    earliest_days = max(0, (position - 1) // capacity)
    latest_days = earliest_days + max(1, int(os.getenv("VIDEO_REQUEST_ETA_RANGE_DAYS", "2")))
    today = timezone.localdate()
    return (
        (today + timedelta(days=earliest_days)).isoformat(),
        (today + timedelta(days=latest_days)).isoformat(),
    )
