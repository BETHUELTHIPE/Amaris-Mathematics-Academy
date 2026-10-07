from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.utils import timezone

from content.models import StudentRecord, TutorAvailabilitySlot, VideoRequest

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

# Server-owned price. The browser never supplies or influences the amount.
VIDEO_REQUEST_PRICE = Decimal("150.00")

_VALID_PROGRAMMES = {choice.value for choice in TutorAvailabilitySlot.Programme}
_VALID_SUBJECTS = {choice.value for choice in TutorAvailabilitySlot.Subject}


@dataclass(frozen=True)
class VideoRequestCheckoutSession:
    request_reference: str
    gateway_url: str
    fields: dict[str, str]


def _public_urls() -> tuple[str, str, str]:
    site_url = os.getenv(
        "PUBLIC_SITE_URL",
        "https://amaris-mathematics-academy.bethuelthipe.chatgpt.site",
    ).rstrip("/")
    api_url = os.getenv("PUBLIC_API_URL", "").rstrip("/")
    return_url = os.getenv(
        "PAYFAST_VIDEO_REQUEST_RETURN_URL",
        f"{site_url}/request-video/confirmation",
    ).strip()
    cancel_url = os.getenv(
        "PAYFAST_VIDEO_REQUEST_CANCEL_URL",
        f"{site_url}/payments/cancelled",
    ).strip()
    notify_url = os.getenv(
        "PAYFAST_NOTIFY_URL",
        f"{api_url}/api/v1/payfast/itn/" if api_url else "",
    ).strip()
    return return_url, cancel_url, notify_url


def create_video_request_checkout(
    *,
    student: StudentRecord,
    programme: str,
    subject: str,
    level: str,
    topic: str,
    details: str,
    idempotency_key: str,
) -> VideoRequestCheckoutSession:
    key = idempotency_key.strip()
    cleaned_programme = str(programme).strip().lower()
    cleaned_subject = str(subject).strip().lower()
    cleaned_level = " ".join(str(level).split()).strip()
    cleaned_topic = " ".join(str(topic).split()).strip()
    cleaned_details = str(details).strip()

    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", key):
        raise PaymentSecurityError("Invalid request idempotency key.")
    if cleaned_programme not in _VALID_PROGRAMMES:
        raise PaymentSecurityError("Choose a valid programme.")
    if cleaned_subject not in _VALID_SUBJECTS:
        raise PaymentSecurityError("Choose a valid subject.")
    if not cleaned_level or len(cleaned_level) > 80:
        raise PaymentSecurityError("Enter a valid grade or level.")
    if len(cleaned_topic) < 2 or len(cleaned_topic) > 180:
        raise PaymentSecurityError("Enter a video topic between 2 and 180 characters.")
    if len(cleaned_details) > 2000:
        raise PaymentSecurityError("Request details must be 2000 characters or fewer.")
    if not student.is_active:
        raise PaymentSecurityError("Inactive students cannot request videos.")

    now = timezone.now()
    reference = f"VRQ-{key}"
    with transaction.atomic():
        existing = VideoRequest.objects.select_for_update().filter(idempotency_key=key).first()
        if existing is not None:
            same_request = (
                existing.student_id == student.pk
                and existing.programme == cleaned_programme
                and existing.subject == cleaned_subject
                and existing.level == cleaned_level
                and existing.topic == cleaned_topic
            )
            if not same_request:
                raise PaymentSecurityError("This request key is already bound to another video request.")
            if existing.status in {
                VideoRequest.Status.PAID,
                VideoRequest.Status.FULFILLED,
            }:
                raise PaymentSecurityError("This video request has already been paid.")
            if existing.status in {
                VideoRequest.Status.EXPIRED,
                VideoRequest.Status.CANCELLED,
            }:
                existing.status = VideoRequest.Status.PENDING_PAYMENT
                existing.hold_expires_at = now + timedelta(minutes=30)
                existing.provider_reference = ""
                existing.paid_at = None
                existing.gateway_verified_at = None
                existing.invoice_number = None
                existing.save(
                    update_fields=(
                        "status",
                        "hold_expires_at",
                        "provider_reference",
                        "paid_at",
                        "gateway_verified_at",
                        "invoice_number",
                        "updated_at",
                    )
                )
            request_obj = existing
        else:
            try:
                request_obj = VideoRequest.objects.create(
                    reference=reference,
                    idempotency_key=key,
                    student=student,
                    programme=cleaned_programme,
                    subject=cleaned_subject,
                    level=cleaned_level,
                    topic=cleaned_topic,
                    details=cleaned_details,
                    amount=VIDEO_REQUEST_PRICE,
                    currency="ZAR",
                    status=VideoRequest.Status.PENDING_PAYMENT,
                )
            except IntegrityError as exc:
                raise PaymentSecurityError("This video request could not be created.") from exc

    merchant_id, merchant_key, passphrase = _payfast_credentials()
    return_url, cancel_url, notify_url = _public_urls()
    fields = {
        "merchant_id": merchant_id,
        "merchant_key": merchant_key,
        "return_url": f"{return_url}?reference={request_obj.reference}",
        "cancel_url": f"{cancel_url}?reference={request_obj.reference}",
        "notify_url": notify_url,
        "name_first": student.first_name[:100],
        "name_last": student.last_name[:100],
        "email_address": student.email[:100],
        "m_payment_id": request_obj.reference,
        "amount": f"{request_obj.amount:.2f}",
        "item_name": "Amaris custom maths video request",
        "custom_str1": str(student.supabase_user_id),
        "custom_str2": request_obj.reference,
    }
    fields = {name: value for name, value in fields.items() if value != ""}
    fields["signature"] = generate_payfast_signature(fields, passphrase)
    return VideoRequestCheckoutSession(
        request_reference=request_obj.reference,
        gateway_url=PAYFAST_SANDBOX_URL if _payfast_mode() == "sandbox" else PAYFAST_LIVE_URL,
        fields=fields,
    )


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
        request_obj = VideoRequest.objects.select_related("student").get(reference=reference)
    except VideoRequest.DoesNotExist:
        return NotificationResult(False, "pending_payment", reason="unknown_request")

    if request_obj.status in {VideoRequest.Status.PAID, VideoRequest.Status.FULFILLED}:
        if request_obj.provider_reference == provider_reference:
            return NotificationResult(
                True,
                request_obj.status,
                reason="duplicate_callback",
                duplicate=True,
            )
        return NotificationResult(
            False,
            request_obj.status,
            reason="provider_reference_replay",
            duplicate=True,
        )

    if (
        request_obj.status == VideoRequest.Status.PENDING_PAYMENT
        and request_obj.hold_expires_at <= timezone.now()
    ):
        request_obj.status = VideoRequest.Status.EXPIRED
        request_obj.save(update_fields=("status", "updated_at"))
        return NotificationResult(False, request_obj.status, reason="request_hold_expired")

    try:
        verified = gateway.verify_notification(payload)
    except TimeoutError:
        return NotificationResult(
            False,
            request_obj.status,
            reason="verification_timeout",
            retryable=True,
        )
    except (ConnectionError, OSError):
        return NotificationResult(
            False,
            request_obj.status,
            reason="verification_network_failure",
            retryable=True,
        )
    if not verified:
        return NotificationResult(False, request_obj.status, reason="invalid_callback")

    if request_obj.provider_reference and request_obj.provider_reference != provider_reference:
        return NotificationResult(False, request_obj.status, reason="provider_reference_replay")
    if VideoRequest.objects.filter(provider_reference=provider_reference).exclude(pk=request_obj.pk).exists():
        return NotificationResult(False, request_obj.status, reason="provider_reference_replay")

    amount = _decimal(payload.get("amount_gross"))
    if amount is None or amount != request_obj.amount:
        return NotificationResult(False, request_obj.status, reason="tampered_amount")
    if str(payload.get("custom_str1", "")).strip() != str(request_obj.student.supabase_user_id):
        return NotificationResult(False, request_obj.status, reason="wrong_student")
    if str(payload.get("custom_str2", "")).strip() != request_obj.reference:
        return NotificationResult(False, request_obj.status, reason="wrong_service")

    with transaction.atomic():
        request_obj = VideoRequest.objects.select_for_update().select_related("student").get(pk=request_obj.pk)
        request_obj.provider_reference = provider_reference
        request_obj.gateway_verified_at = timezone.now()

        if gateway_status == "COMPLETE":
            request_obj.status = VideoRequest.Status.PAID
            request_obj.paid_at = timezone.now()
            if not request_obj.invoice_number:
                request_obj.invoice_number = (
                    f"INV-VID-{request_obj.paid_at:%Y%m%d}-{str(request_obj.pk).replace('-', '')[:10].upper()}"
                )
        elif gateway_status in {"FAILED", "CANCELLED"}:
            request_obj.status = VideoRequest.Status.CANCELLED

        request_obj.save(
            update_fields=(
                "provider_reference",
                "gateway_verified_at",
                "status",
                "paid_at",
                "invoice_number",
                "updated_at",
            )
        )

    return NotificationResult(True, request_obj.status)
