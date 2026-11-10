"""Paystack hosted checkout and authoritative server-side transaction verification."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.db import transaction
from django.utils import timezone

from content.models import LiveClassBooking, Payment
from .payments import PaymentSecurityError, _fulfill_verified_payment

PAYSTACK_API = "https://api.paystack.co"


def enabled() -> bool:
    return os.getenv("PAYSTACK_ENABLED", "false").lower() == "true"


def _secret() -> str:
    key = os.getenv("PAYSTACK_SECRET_KEY", "")
    if not enabled() or not key.startswith(("sk_test_", "sk_live_")):
        raise PaymentSecurityError("Paystack is not enabled or configured.")
    return key


def _request(path: str, *, payload: dict | None = None) -> dict:
    key = _secret()
    url = f"{PAYSTACK_API}{path}"
    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        method="POST" if payload is not None else "GET",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=10) as response:
            result = json.load(response)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise PaymentSecurityError("Paystack is temporarily unavailable.") from exc
    if not result.get("status") or not isinstance(result.get("data"), dict):
        raise PaymentSecurityError("Paystack did not confirm this transaction request.")
    return result["data"]


def initialize(*, email: str, amount: Decimal, reference: str, callback_path: str) -> str:
    """Server-owned ZAR cents and fixed trusted return origin; no browser success claims."""
    site_url = os.getenv("PUBLIC_SITE_URL", "").rstrip("/")
    if not site_url.startswith("https://"):
        raise PaymentSecurityError("A secure public site URL is required.")
    cents = int(amount * 100)
    if amount <= 0 or Decimal(cents) / 100 != amount:
        raise PaymentSecurityError("Invalid ZAR payment amount.")
    data = _request(
        "/transaction/initialize",
        payload={
            "email": email,
            "amount": cents,
            "currency": "ZAR",
            "reference": reference,
            "callback_url": f"{site_url}{callback_path}?reference={quote(reference)}",
        },
    )
    url = str(data.get("authorization_url", ""))
    if not url.startswith("https://checkout.paystack.com/"):
        raise PaymentSecurityError("Paystack returned an unsafe checkout URL.")
    if data.get("reference") != reference:
        raise PaymentSecurityError("Paystack reference mismatch.")
    return url


def verify_and_settle(reference: str) -> str:
    """Called only after a signed webhook; verify amount and status with Paystack."""
    if not reference or len(reference) > 100:
        raise PaymentSecurityError("Invalid reference.")
    data = _request(f"/transaction/verify/{quote(reference, safe='')}")
    if data.get("reference") != reference or data.get("status") != "success":
        raise PaymentSecurityError("Transaction is not successful.")
    if data.get("currency") != "ZAR":
        raise PaymentSecurityError("Incorrect transaction currency.")
    try:
        actual_amount = int(data.get("amount"))
    except (TypeError, ValueError) as exc:
        raise PaymentSecurityError("Invalid payment amount.") from exc
    provider_id = str(data.get("id", ""))
    if not provider_id or not provider_id.isdigit():
        raise PaymentSecurityError("Missing Paystack transaction ID.")
    with transaction.atomic():
        if reference.startswith("LCB-"):
            booking = LiveClassBooking.objects.select_for_update().select_related("slot").get(reference=reference)
            if booking.payment_provider != "paystack" or actual_amount != int(booking.amount * 100):
                raise PaymentSecurityError("Booking provider or amount mismatch.")
            if booking.status == LiveClassBooking.Status.CONFIRMED:
                if booking.provider_reference == provider_id:
                    return "already_confirmed"
                raise PaymentSecurityError("Conflicting transaction for confirmed booking.")
            if (
                booking.status != LiveClassBooking.Status.PENDING_PAYMENT
                or booking.hold_expires_at <= timezone.now()
                raise PaymentSecurityError("Booking is no longer payable; review refund manually.")
            if LiveClassBooking.objects.exclude(pk=booking.pk).filter(provider_reference=provider_id).exists():
                raise PaymentSecurityError("Transaction replay.")
            booking.status = LiveClassBooking.Status.CONFIRMED
            booking.provider_reference = provider_id
            booking.gateway_verified_at = timezone.now()
            booking.paid_at = timezone.now()
            booking.invoice_number = booking.invoice_number or (
                f"INV-LIVE-{booking.paid_at:%Y%m%d}-{str(booking.pk).replace('-', '')[:10].upper()}"
            )
            booking.save(update_fields=["status", "provider_reference", "gateway_verified_at", "paid_at", "invoice_number", "updated_at"])
            return "confirmed"
        payment = Payment.objects.select_for_update().select_related("student", "course").get(reference=reference)
        if payment.provider != Payment.Provider.PAYSTACK or actual_amount != int(payment.amount * 100):
            raise PaymentSecurityError("Course provider or amount mismatch.")
        if payment.status == Payment.Status.PAID:
            if payment.provider_reference == provider_id:
                return "already_paid"
            raise PaymentSecurityError("Conflicting transaction for paid course.")
        if payment.status != Payment.Status.PENDING:
            raise PaymentSecurityError("Payment is no longer pending.")
        if Payment.objects.exclude(pk=payment.pk).filter(provider_reference=provider_id).exists():
            raise PaymentSecurityError("Transaction replay.")
        payment.status = Payment.Status.PAID
        payment.provider_reference = provider_id
        payment.gateway_verified_at = timezone.now()
        payment.verification_source = "paystack_server_verification"
        payment.paid_at = timezone.now()
        payment.save(update_fields=["status", "provider_reference", "gateway_verified_at", "verification_source", "paid_at", "updated_at"])
        _fulfill_verified_payment(payment)
        return "paid"
