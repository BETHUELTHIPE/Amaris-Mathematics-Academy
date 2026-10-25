"""PayFast-verified topical video checkout. No student-controlled pricing or paid flags."""

import os
import re
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from content.models import LiveClassBooking, Payment
from content.services.live_classes import _public_urls
from content.services.payments import (
    PAYFAST_LIVE_URL,
    PAYFAST_SANDBOX_URL,
    CheckoutSession,
    NotificationResult,
    PaymentSecurityError,
    _payfast_credentials,
    _payfast_mode,
    generate_payfast_signature,
)
from content.services.tutor_finance import _contract_for, record_topical_video_sale
from content.tutor_finance_models import TutorContract, TutorVideoRequest


def video_price():
    try:
        price = Decimal(os.getenv("TUTOR_TOPICAL_VIDEO_PRICE_ZAR", "450.00"))
    except InvalidOperation as exc:
        raise PaymentSecurityError("Topical video pricing is not configured.") from exc
    if not price.is_finite() or price <= 0 or price != price.quantize(Decimal("0.01")):
        raise PaymentSecurityError("Topical video price must be a positive ZAR amount.")
    return price


def create_video_checkout(*, student, tutor, programme, topic, idempotency_key):
    key = idempotency_key.strip()
    cleaned_topic = " ".join(topic.split()).strip()
    cleaned_programme = " ".join(programme.split()).strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", key):
        raise PaymentSecurityError("Invalid topical video checkout key.")
    if len(cleaned_topic) < 2 or len(cleaned_topic) > 180 or len(cleaned_programme) < 2 or len(cleaned_programme) > 60:
        raise PaymentSecurityError("Supply a valid programme and topic.")
    if not student.is_active or not tutor.is_active:
        raise PaymentSecurityError("Student or tutor account is inactive.")
    price = video_price()
    if not _contract_for(tutor.pk, TutorContract.Service.VIDEO, timezone.now()):
        raise PaymentSecurityError("This tutor is not available for paid video requests.")
    reference = f"TVR-{key}"
    with transaction.atomic():
        order, created = TutorVideoRequest.objects.get_or_create(
            idempotency_key=key,
            defaults=dict(
                reference=reference,
                student=student,
                tutor=tutor,
                programme=cleaned_programme,
                topic=cleaned_topic,
                price=price,
                currency="ZAR",
            ),
        )
        if not created:
            if (
                order.student_id != student.pk
                or order.tutor_id != tutor.pk
                or order.programme != cleaned_programme
                or order.topic != cleaned_topic
                or order.price != price
            ):
                raise PaymentSecurityError("Checkout key was already used for another order.")
            if order.status != TutorVideoRequest.Status.PENDING:
                raise PaymentSecurityError("This topical video order is no longer pending.")

    merchant_id, merchant_key, passphrase = _payfast_credentials()
    return_url, cancel_url, notify_url = _public_urls()
    fields = {
        "merchant_id": merchant_id,
        "merchant_key": merchant_key,
        "return_url": f"{return_url}?reference={reference}",
        "cancel_url": f"{cancel_url}?reference={reference}",
        "notify_url": notify_url,
        "name_first": student.first_name[:100],
        "name_last": student.last_name[:100],
        "email_address": student.email[:100],
        "m_payment_id": reference,
        "amount": f"{order.price:.2f}",
        "item_name": "Amaris topical video request",
        "custom_str1": str(student.supabase_user_id),
        "custom_str2": reference,
    }
    fields = {name: value for name, value in fields.items() if value}
    fields["signature"] = generate_payfast_signature(fields, passphrase)
    return CheckoutSession(
        payment_reference=reference,
        gateway_url=PAYFAST_SANDBOX_URL if _payfast_mode() == "sandbox" else PAYFAST_LIVE_URL,
        fields=fields,
    )


def process_video_notification(payload, *, gateway):
    reference = str(payload.get("m_payment_id", "")).strip()
    provider_ref = str(payload.get("pf_payment_id", "")).strip()
    status = str(payload.get("payment_status", "")).strip().upper()
    if not reference or not provider_ref or status not in {"COMPLETE", "FAILED", "CANCELLED", "PENDING"}:
        return NotificationResult(False, "pending", reason="invalid_payment_event")
    order = TutorVideoRequest.objects.select_related("student", "tutor").filter(reference=reference).first()
    if not order:
        return NotificationResult(False, "pending", reason="unknown_video_request")
    if order.status in {TutorVideoRequest.Status.PAID, TutorVideoRequest.Status.DELIVERED}:
        if status == "COMPLETE" and order.provider_reference == provider_ref:
            return NotificationResult(True, order.status, reason="duplicate_callback", duplicate=True)
        return NotificationResult(False, order.status, reason="immutable_paid_video")
    try:
        verified = gateway.verify_notification(payload)
    except (TimeoutError, ConnectionError, OSError):
        return NotificationResult(False, order.status, reason="gateway_unavailable", retryable=True)
    if not verified:
        return NotificationResult(False, order.status, reason="unverified_event")
    try:
        amount = Decimal(str(payload.get("amount_gross", "")))
    except (InvalidOperation, ValueError):
        return NotificationResult(False, order.status, reason="invalid_amount")
    if (
        amount != order.price
        or str(payload.get("custom_str1", "")) != str(order.student.supabase_user_id)
        or str(payload.get("custom_str2", "")) != order.reference
    ):
        return NotificationResult(False, order.status, reason="payment_mismatch")
    if (
        Payment.objects.filter(provider_reference=provider_ref).exists()
        or LiveClassBooking.objects.filter(provider_reference=provider_ref).exists()
        or TutorVideoRequest.objects.filter(provider_reference=provider_ref).exclude(pk=order.pk).exists()
    ):
        return NotificationResult(False, order.status, reason="duplicate_gateway_reference")
    with transaction.atomic():
        locked = TutorVideoRequest.objects.select_for_update().get(pk=order.pk)
        if locked.status != TutorVideoRequest.Status.PENDING:
            return NotificationResult(False, locked.status, reason="not_pending")
        if locked.provider_reference and locked.provider_reference != provider_ref:
            return NotificationResult(False, locked.status, reason="replayed_reference")
        locked.provider_reference = provider_ref
        locked.gateway_verified_at = timezone.now()
        if status == "COMPLETE":
            locked.status = TutorVideoRequest.Status.PAID
            locked.paid_at = timezone.now()
        elif status in {"CANCELLED", "FAILED"}:
            locked.status = TutorVideoRequest.Status.CANCELLED
        locked.save(update_fields=["provider_reference", "gateway_verified_at", "status", "paid_at", "updated_at"])
        if locked.status == TutorVideoRequest.Status.PAID:
            record_topical_video_sale(locked)
    return NotificationResult(True, locked.status)
