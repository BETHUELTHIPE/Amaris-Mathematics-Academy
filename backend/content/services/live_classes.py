from __future__ import annotations

import os
import re
from datetime import timedelta
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.utils import timezone

from content.models import LiveClassBooking, StudentRecord, TutorAvailabilitySlot

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

LIVE_CLASS_PRICE = Decimal("250.00")


@dataclass(frozen=True)
class LiveClassCheckoutSession:
    booking_reference: str
    gateway_url: str
    fields: dict[str, str]


def _public_urls() -> tuple[str, str, str]:
    site_url = os.getenv(
        "PUBLIC_SITE_URL",
        "https://amaris-mathematics-academy.bethuelthipe.chatgpt.site",
    ).rstrip("/")
    api_url = os.getenv("PUBLIC_API_URL", "").rstrip("/")
    return_url = os.getenv(
        "PAYFAST_LIVE_CLASS_RETURN_URL",
        f"{site_url}/book-online-live-class/confirmation",
    ).strip()
    cancel_url = os.getenv(
        "PAYFAST_LIVE_CLASS_CANCEL_URL",
        f"{site_url}/payments/cancelled",
    ).strip()
    notify_url = os.getenv(
        "PAYFAST_NOTIFY_URL",
        f"{api_url}/api/v1/payfast/itn/" if api_url else "",
    ).strip()
    return return_url, cancel_url, notify_url


def create_live_class_checkout(
    *,
    student: StudentRecord,
    slot: TutorAvailabilitySlot,
    topic: str,
    idempotency_key: str,
) -> LiveClassCheckoutSession:
    key = idempotency_key.strip()
    cleaned_topic = " ".join(topic.split()).strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", key):
        raise PaymentSecurityError("Invalid booking idempotency key.")
    if len(cleaned_topic) < 2 or len(cleaned_topic) > 180:
        raise PaymentSecurityError("Enter a class topic between 2 and 180 characters.")
    if not student.is_active:
        raise PaymentSecurityError("Inactive students cannot book live classes.")

    now = timezone.now()
    reference = f"LCB-{key}"
    with transaction.atomic():
        locked_slot = (
            TutorAvailabilitySlot.objects.select_for_update()
            .select_related("tutor")
            .get(pk=slot.pk)
        )
        if not locked_slot.is_active or locked_slot.starts_at <= now:
            raise PaymentSecurityError("This tutor slot is no longer available.")
        if not locked_slot.zoom_join_url:
            raise PaymentSecurityError("This tutor slot is not ready for Zoom booking.")

        LiveClassBooking.objects.filter(
            slot=locked_slot,
            status=LiveClassBooking.Status.PENDING_PAYMENT,
            hold_expires_at__lte=now,
        ).update(status=LiveClassBooking.Status.EXPIRED)

        existing = LiveClassBooking.objects.filter(idempotency_key=key).first()
        if existing is not None:
            same_booking = (
                existing.student_id == student.pk
                and existing.slot_id == locked_slot.pk
                and existing.topic == cleaned_topic
            )
            if not same_booking:
                raise PaymentSecurityError(
                    "This booking key is already bound to another live class."
                )
            if existing.status == LiveClassBooking.Status.CONFIRMED:
                raise PaymentSecurityError("This live class is already confirmed.")
            if existing.status in {
                LiveClassBooking.Status.EXPIRED,
                LiveClassBooking.Status.CANCELLED,
            }:
                if LiveClassBooking.objects.filter(
                    slot=locked_slot,
                    status__in=(
                        LiveClassBooking.Status.PENDING_PAYMENT,
                        LiveClassBooking.Status.CONFIRMED,
                    ),
                ).exclude(pk=existing.pk).exists():
                    raise PaymentSecurityError("This tutor slot has already been booked.")
                existing.status = LiveClassBooking.Status.PENDING_PAYMENT
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
            booking = existing
        else:
            if LiveClassBooking.objects.filter(
                slot=locked_slot,
                status__in=(
                    LiveClassBooking.Status.PENDING_PAYMENT,
                    LiveClassBooking.Status.CONFIRMED,
                ),
            ).exists():
                raise PaymentSecurityError("This tutor slot has already been booked.")
            try:
                booking = LiveClassBooking.objects.create(
                    reference=reference,
                    idempotency_key=key,
                    student=student,
                    slot=locked_slot,
                    programme=locked_slot.programme,
                    subject=locked_slot.subject,
                    level=locked_slot.level,
                    topic=cleaned_topic,
                    amount=LIVE_CLASS_PRICE,
                    currency="ZAR",
                    status=LiveClassBooking.Status.PENDING_PAYMENT,
                )
            except IntegrityError as exc:
                raise PaymentSecurityError("This tutor slot has already been booked.") from exc

    merchant_id, merchant_key, passphrase = _payfast_credentials()
    return_url, cancel_url, notify_url = _public_urls()
    fields = {
        "merchant_id": merchant_id,
        "merchant_key": merchant_key,
        "return_url": f"{return_url}?reference={booking.reference}",
        "cancel_url": f"{cancel_url}?reference={booking.reference}",
        "notify_url": notify_url,
        "name_first": student.first_name[:100],
        "name_last": student.last_name[:100],
        "email_address": student.email[:100],
        "m_payment_id": booking.reference,
        "amount": f"{booking.amount:.2f}",
        "item_name": "Amaris 1-hour Zoom live class",
        "custom_str1": str(student.supabase_user_id),
        "custom_str2": booking.reference,
    }
    fields = {key: value for key, value in fields.items() if value != ""}
    fields["signature"] = generate_payfast_signature(fields, passphrase)
    return LiveClassCheckoutSession(
        booking_reference=booking.reference,
        gateway_url=PAYFAST_SANDBOX_URL if _payfast_mode() == "sandbox" else PAYFAST_LIVE_URL,
        fields=fields,
    )


def _decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def process_live_class_notification(
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
        booking = LiveClassBooking.objects.select_related("student", "slot").get(
            reference=reference
        )
    except LiveClassBooking.DoesNotExist:
        return NotificationResult(False, "pending_payment", reason="unknown_booking")

    if booking.status == LiveClassBooking.Status.CONFIRMED:
        if booking.provider_reference == provider_reference:
            return NotificationResult(
                True,
                booking.status,
                reason="duplicate_callback",
                duplicate=True,
            )
        return NotificationResult(
            False,
            booking.status,
            reason="provider_reference_replay",
            duplicate=True,
        )

    if (
        booking.status == LiveClassBooking.Status.PENDING_PAYMENT
        and booking.hold_expires_at <= timezone.now()
    ):
        booking.status = LiveClassBooking.Status.EXPIRED
        booking.save(update_fields=("status", "updated_at"))
        return NotificationResult(False, booking.status, reason="booking_hold_expired")

    try:
        verified = gateway.verify_notification(payload)
    except TimeoutError:
        return NotificationResult(
            False,
            booking.status,
            reason="verification_timeout",
            retryable=True,
        )
    except (ConnectionError, OSError):
        return NotificationResult(
            False,
            booking.status,
            reason="verification_network_failure",
            retryable=True,
        )
    if not verified:
        return NotificationResult(False, booking.status, reason="invalid_callback")

    amount = _decimal(payload.get("amount_gross"))
    if amount is None or amount != booking.amount:
        return NotificationResult(False, booking.status, reason="tampered_amount")
    if str(payload.get("custom_str1", "")).strip() != str(
        booking.student.supabase_user_id
    ):
        return NotificationResult(False, booking.status, reason="wrong_student")
    if str(payload.get("custom_str2", "")).strip() != booking.reference:
        return NotificationResult(False, booking.status, reason="wrong_service")

    with transaction.atomic():
        booking = (
            LiveClassBooking.objects.select_for_update()
            .select_related("student", "slot")
            .get(pk=booking.pk)
        )
        booking.provider_reference = provider_reference
        booking.gateway_verified_at = timezone.now()

        if gateway_status == "COMPLETE":
            if booking.slot.starts_at <= timezone.now():
                return NotificationResult(
                    False,
                    booking.status,
                    reason="class_already_started",
                )
            booking.status = LiveClassBooking.Status.CONFIRMED
            booking.paid_at = timezone.now()
            if not booking.invoice_number:
                booking.invoice_number = (
                    f"INV-LIVE-{booking.paid_at:%Y%m%d}-{str(booking.pk).replace('-', '')[:10].upper()}"
                )
        elif gateway_status in {"FAILED", "CANCELLED"}:
            booking.status = LiveClassBooking.Status.CANCELLED

        booking.save(
            update_fields=(
                "provider_reference",
                "gateway_verified_at",
                "status",
                "paid_at",
                "invoice_number",
                "updated_at",
            )
        )

    return NotificationResult(True, booking.status)
