from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from content.models import LiveClassBooking, StudentRecord, TutorAvailabilitySlot

from . import paystack
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

LIVE_CLASS_PRICE = Decimal("250.00")  # Per booked hour, not per session.


def price_for_live_class_slot(slot: TutorAvailabilitySlot) -> Decimal:
    hours = slot.duration_hours
    if not hours:
        raise PaymentSecurityError("This tutor slot has an invalid duration.")
    return LIVE_CLASS_PRICE * hours


@dataclass(frozen=True)
class LiveClassCheckoutSession:
    booking_reference: str
    gateway_url: str
    fields: dict[str, str]
    payment_provider: str = LiveClassBooking.PaymentProvider.PAYFAST
    test_mode: bool = False


def _public_urls() -> tuple[str, str, str]:
    site_url = os.getenv(
        "PUBLIC_SITE_URL",
        DEFAULT_PUBLIC_SITE_URL,
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
        build_payfast_notify_url(api_url),
    ).strip()
    return return_url, cancel_url, notify_url


def create_live_class_checkout(
    *,
    student: StudentRecord,
    slot: TutorAvailabilitySlot,
    topic: str,
    idempotency_key: str,
    payment_provider: str = LiveClassBooking.PaymentProvider.PAYFAST,
) -> LiveClassCheckoutSession:
    key = idempotency_key.strip()
    cleaned_topic = " ".join(topic.split()).strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", key):
        raise PaymentSecurityError("Invalid booking idempotency key.")
    if len(cleaned_topic) < 2 or len(cleaned_topic) > 180:
        raise PaymentSecurityError("Enter a class topic between 2 and 180 characters.")
    if not student.is_active:
        raise PaymentSecurityError("Inactive students cannot book live classes.")

    first_name = " ".join(student.first_name.split())
    last_name = " ".join(student.last_name.split())
    if (
        len(first_name) < 2
        or len(last_name) < 2
        or (first_name.casefold(), last_name.casefold()) == ("student", "learner")
    ):
        raise PaymentSecurityError("Complete your registered first and last name before booking.")
    if payment_provider not in LiveClassBooking.PaymentProvider.values:
        raise PaymentSecurityError("Unknown payment provider.")
    using_paystack = payment_provider == LiveClassBooking.PaymentProvider.PAYSTACK
    if using_paystack and not paystack.checkout_enabled():
        raise PaymentSecurityError("Paystack checkout is unavailable.")

    now = timezone.now()
    reference = paystack.booking_reference(key) if using_paystack else f"LCB-{key}"
    with transaction.atomic():
        locked_slot = TutorAvailabilitySlot.objects.select_for_update().select_related("tutor").get(pk=slot.pk)
        if not locked_slot.is_active or locked_slot.starts_at <= now:
            raise PaymentSecurityError("This tutor slot is no longer available.")
        if not locked_slot.zoom_join_url:
            raise PaymentSecurityError("This tutor slot is not ready for Zoom booking.")
        amount = price_for_live_class_slot(locked_slot)
        # Serialize checkouts for the same tutor to prevent two overlapping
        # published slots from both accepting a payment at the same time.
        get_user_model().objects.select_for_update().get(pk=locked_slot.tutor_id)
        overlapping_bookings = (
            LiveClassBooking.objects.filter(
                slot__tutor_id=locked_slot.tutor_id,
                slot__starts_at__lt=locked_slot.ends_at,
                slot__ends_at__gt=locked_slot.starts_at,
            )
            .exclude(slot_id=locked_slot.pk)
            .filter(
                Q(status=LiveClassBooking.Status.CONFIRMED)
                | Q(
                    status=LiveClassBooking.Status.PENDING_PAYMENT,
                    hold_expires_at__gt=now,
                )
            )
        )
        if overlapping_bookings.exists():
            raise PaymentSecurityError("This tutor is already booked for overlapping hours.")

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
                raise PaymentSecurityError("This booking key is already bound to another live class.")
            if existing.payment_provider != payment_provider:
                raise PaymentSecurityError("This booking attempt already has a payment provider.")
            if existing.amount != amount:
                raise PaymentSecurityError("The original booking duration or price has changed.")
            if existing.status == LiveClassBooking.Status.CONFIRMED:
                raise PaymentSecurityError("This live class is already confirmed.")
            if existing.status != LiveClassBooking.Status.PENDING_PAYMENT:
                raise PaymentSecurityError("This checkout attempt has ended. Choose an available tutor time again.")
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
                    amount=amount,
                    currency="ZAR",
                    payment_provider=payment_provider,
                    paystack_mode=paystack.mode() if using_paystack else "",
                    status=LiveClassBooking.Status.PENDING_PAYMENT,
                )
            except IntegrityError as exc:
                raise PaymentSecurityError("This tutor slot has already been booked.") from exc

    if using_paystack:
        return _paystack_checkout(booking.pk)

    merchant_id, merchant_key, passphrase = _payfast_credentials()
    return_url, cancel_url, notify_url = _public_urls()
    if _payfast_mode() == "live" and any(
        urlparse(url).scheme != "https" or not urlparse(url).netloc for url in (return_url, cancel_url, notify_url)
    ):
        raise PaymentSecurityError("Live PayFast return, cancel, and notification URLs must be configured for HTTPS.")
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
        "item_name": f"Amaris {locked_slot.duration_hours}-hour Zoom live class",
        "custom_str1": str(student.supabase_user_id),
        "custom_str2": booking.reference,
    }
    fields = {key: value for key, value in fields.items() if value != ""}
    fields["signature"] = generate_payfast_signature(fields, passphrase)
    return LiveClassCheckoutSession(
        booking_reference=booking.reference,
        gateway_url=PAYFAST_SANDBOX_URL if _payfast_mode() == "sandbox" else PAYFAST_LIVE_URL,
        fields=fields,
        test_mode=_payfast_mode() == "sandbox",
    )


def _paystack_checkout(booking_id) -> LiveClassCheckoutSession:
    # The slot transaction has committed. Lock only this booking while
    # initializing to prevent parallel requests creating separate checkouts.
    with transaction.atomic():
        booking = (
            LiveClassBooking.objects.select_for_update(of=("self",))
            .select_related("student", "slot")
            .get(pk=booking_id)
        )
        now = timezone.now()
        if (
            booking.status != LiveClassBooking.Status.PENDING_PAYMENT
            or booking.hold_expires_at <= now
            or booking.slot.starts_at <= now
        ):
            raise PaymentSecurityError("This checkout attempt has ended. Choose an available tutor time again.")
        if booking.paystack_mode != paystack.mode():
            raise PaymentSecurityError("The original Paystack payment mode has changed.")
        if not booking.paystack_checkout_url:
            booking.paystack_checkout_url = paystack.initialize(
                email=booking.student.email, amount=booking.amount, reference=booking.reference
            )
            booking.save(update_fields=("paystack_checkout_url", "updated_at"))
        return LiveClassCheckoutSession(
            booking_reference=booking.reference,
            gateway_url=booking.paystack_checkout_url,
            fields={},
            payment_provider=booking.payment_provider,
            test_mode=paystack.mode() == "test",
        )


def _record_verified_charge(booking: LiveClassBooking, paid_at) -> None:
    booking.paid_at = paid_at
    if (
        booking.status != LiveClassBooking.Status.PENDING_PAYMENT
        or booking.hold_expires_at <= paid_at
        or booking.slot.starts_at <= paid_at
    ):
        # A late verified charge needs reconciliation and cannot claim a released slot.
        booking.status = LiveClassBooking.Status.PAYMENT_REVIEW
        return
    booking.status = LiveClassBooking.Status.CONFIRMED
    booking.invoice_number = f"INV-LIVE-{paid_at:%Y%m%d}-{booking.pk.hex[:10].upper()}"


def process_paystack_live_class_payment(reference: str) -> str:
    provider = LiveClassBooking.PaymentProvider.PAYSTACK
    bookings = LiveClassBooking.objects.filter(payment_provider=provider)
    if not bookings.filter(reference=reference).exists():
        return "ignored"

    amount, provider_reference = paystack.verified_payment(reference)
    with transaction.atomic():
        booking = bookings.select_for_update(of=("self",)).select_related("slot").get(reference=reference)
        if booking.paystack_mode != paystack.mode():
            raise PaymentSecurityError("Paystack booking mode mismatch.")
        if booking.currency != "ZAR" or amount != booking.amount * 100:
            raise PaymentSecurityError("Paystack booking amount or currency mismatch.")
        if booking.provider_reference == provider_reference:
            return booking.status
        if booking.provider_reference or bookings.filter(provider_reference=provider_reference).exists():
            raise PaymentSecurityError("Paystack transaction is already linked to a booking.")

        booking.provider_reference = provider_reference
        booking.gateway_verified_at = timezone.now()
        _record_verified_charge(booking, booking.gateway_verified_at)
        booking.save(
            update_fields=(
                "provider_reference",
                "gateway_verified_at",
                "paid_at",
                "status",
                "invoice_number",
                "updated_at",
            )
        )
        return booking.status


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
        booking = LiveClassBooking.objects.select_related("student", "slot").get(reference=reference)
    except LiveClassBooking.DoesNotExist:
        return NotificationResult(False, "pending_payment", reason="unknown_booking")

    if booking.payment_provider != LiveClassBooking.PaymentProvider.PAYFAST:
        return NotificationResult(False, booking.status, reason="wrong_payment_provider")

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

    if booking.provider_reference and booking.provider_reference != provider_reference:
        return NotificationResult(
            False,
            booking.status,
            reason="provider_reference_replay",
        )
    if (
        LiveClassBooking.objects.filter(
            payment_provider=LiveClassBooking.PaymentProvider.PAYFAST, provider_reference=provider_reference
        )
        .exclude(pk=booking.pk)
        .exists()
    ):
        return NotificationResult(
            False,
            booking.status,
            reason="provider_reference_replay",
        )

    amount = _decimal(payload.get("amount_gross"))
    if amount is None or amount != booking.amount:
        return NotificationResult(False, booking.status, reason="tampered_amount")
    if str(payload.get("custom_str1", "")).strip() != str(booking.student.supabase_user_id):
        return NotificationResult(False, booking.status, reason="wrong_student")
    if str(payload.get("custom_str2", "")).strip() != booking.reference:
        return NotificationResult(False, booking.status, reason="wrong_service")

    with transaction.atomic():
        booking = LiveClassBooking.objects.select_for_update().select_related("student", "slot").get(pk=booking.pk)
        if booking.status == LiveClassBooking.Status.CONFIRMED:
            if booking.provider_reference == provider_reference:
                return NotificationResult(True, booking.status, reason="duplicate_callback", duplicate=True)
            return NotificationResult(False, booking.status, reason="provider_reference_replay")
        if booking.provider_reference and booking.provider_reference != provider_reference:
            return NotificationResult(False, booking.status, reason="provider_reference_replay")
        if booking.status == LiveClassBooking.Status.PAYMENT_REVIEW:
            return NotificationResult(True, booking.status, reason="payment_requires_manual_resolution", duplicate=True)

        booking.provider_reference = provider_reference
        booking.gateway_verified_at = timezone.now()

        if gateway_status == "COMPLETE":
            _record_verified_charge(booking, timezone.now())
        elif gateway_status in {"FAILED", "CANCELLED"}:
            if booking.status == LiveClassBooking.Status.PENDING_PAYMENT:
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
        if booking.status == LiveClassBooking.Status.CONFIRMED:
            from content.services.tutor_finance import record_live_class_sale

            record_live_class_sale(booking)

    return NotificationResult(
        True,
        booking.status,
        reason="payment_requires_manual_resolution" if booking.status == LiveClassBooking.Status.PAYMENT_REVIEW else "",
    )
