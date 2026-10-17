from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import partial
from urllib.parse import urlparse

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils import timezone

from content.donation_models import DonationContribution
from content.services.payments import (
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

logger = logging.getLogger(__name__)
MIN_DONATION = Decimal("20.00")
MAX_DONATION = Decimal("100000.00")


@dataclass(frozen=True)
class DonationCheckout:
    reference: str
    gateway_url: str
    fields: dict[str, str]


def donations_available() -> bool:
    enabled = os.getenv("DONATIONS_ENABLED", "false").lower() == "true"
    if not enabled:
        return False
    try:
        mode = _payfast_mode()
        if mode == "live" and os.getenv("DONATIONS_LIVE_ENABLED", "false").lower() != "true":
            return False
        merchant_id, merchant_key, passphrase = _payfast_credentials()
        # PayFast permits passphrase-free once-off payments for its documented sandbox merchant.
        # Retain the stricter passphrase requirement for live donation activation.
        return bool(merchant_id and merchant_key and (passphrase or mode == "sandbox"))
    except PaymentSecurityError:
        return False


def _require_donations_ready():
    if not donations_available():
        raise PaymentSecurityError("Online contributions are not yet enabled.")


def _checkout_urls(reference: str) -> tuple[str, str, str]:
    site_url = os.getenv("PUBLIC_SITE_URL", DEFAULT_PUBLIC_SITE_URL).rstrip("/")
    api_url = os.getenv("PUBLIC_API_URL", "").rstrip("/")
    notify_url = os.getenv("PAYFAST_NOTIFY_URL", build_payfast_notify_url(api_url)).strip()
    return_url = f"{site_url}/support-our-project/confirmation?reference={reference}"
    cancel_url = f"{site_url}/support-our-project/confirmation?reference={reference}&cancelled=1"
    for name, url in (("return", return_url), ("cancel", cancel_url), ("notify", notify_url)):
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise PaymentSecurityError(f"PayFast {name} URL must be a configured HTTPS endpoint.")
    return return_url, cancel_url, notify_url


def create_donation_checkout(
    *,
    name: str,
    email: str,
    amount: Decimal,
    purpose: str,
    idempotency_key: str,
) -> DonationCheckout:
    _require_donations_ready()
    if not isinstance(amount, Decimal) or not amount.is_finite() or amount != amount.quantize(Decimal("0.01")):
        raise PaymentSecurityError("Enter an amount with no more than two decimal places.")
    if not (MIN_DONATION <= amount <= MAX_DONATION):
        raise PaymentSecurityError("Contribution must be between R20 and R100,000.")
    if purpose not in DonationContribution.Purpose.values:
        raise PaymentSecurityError("Choose a valid contribution purpose.")
    key = idempotency_key.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{12,64}", key):
        raise PaymentSecurityError("Invalid checkout idempotency key.")
    if not name.strip() or not email.strip():
        raise PaymentSecurityError("Name and email are required.")

    # A failed gateway configuration check must never leave a pending donation.
    merchant_id, merchant_key, passphrase = _payfast_credentials()
    reference = "DON-" + key
    return_url, cancel_url, notify_url = _checkout_urls(reference)

    with transaction.atomic():
        donation, created = DonationContribution.objects.get_or_create(
            reference=reference,
            defaults={
                "donor_name": name.strip(),
                "donor_email": email.strip().lower(),
                "amount": amount,
                "purpose": purpose,
            },
        )
        if not created and (
            donation.donor_name != name.strip()
            or donation.donor_email != email.strip().lower()
            or donation.amount != amount
            or donation.purpose != purpose
        ):
            raise PaymentSecurityError("This checkout key belongs to a different contribution.")
        if donation.status != DonationContribution.Status.PENDING:
            raise PaymentSecurityError("Contribution already has a final payment status.")

    fields = {
        "merchant_id": merchant_id,
        "merchant_key": merchant_key,
        "return_url": return_url,
        "cancel_url": cancel_url,
        "notify_url": notify_url,
        "name_first": name.strip()[:100],
        "email_address": email.strip().lower()[:100],
        "m_payment_id": donation.reference,
        "amount": f"{donation.amount:.2f}",
        "item_name": "Amaris education project contribution",
        "item_description": donation.get_purpose_display()[:255],
        "custom_str1": donation.reference,
        "custom_str2": donation.purpose,
    }
    fields["signature"] = generate_payfast_signature(fields, passphrase)
    return DonationCheckout(
        reference=donation.reference,
        gateway_url=PAYFAST_LIVE_URL if _payfast_mode() == "live" else PAYFAST_SANDBOX_URL,
        fields=fields,
    )


def _send_donation_acknowledgement(pk):
    # Best-effort email after the DB commit. Never confuse acknowledgement with a section 18A receipt.
    try:
        donation = DonationContribution.objects.get(pk=pk)
        if donation.receipt_sent_at or donation.status != DonationContribution.Status.PAID:
            return
        send_mail(
            "Amaris contribution payment confirmation",
            (
                f"Thank you for supporting Amaris Mathematics Academy.\n\n"
                f"Reference: {donation.reference}\n"
                f"Amount verified: R{donation.amount:.2f}\n"
                f"Purpose: {donation.get_purpose_display()}\n\n"
                "This is a payment acknowledgement, not a Section 18A tax-deductible donation receipt.\n"
                "For any questions, please contact Amaris using the website contact page.\n"
            ),
            settings.DEFAULT_FROM_EMAIL,
            [donation.donor_email],
            fail_silently=False,
        )
        donation.receipt_sent_at = timezone.now()
        donation.receipt_error = ""
        donation.save(update_fields=["receipt_sent_at", "receipt_error", "updated_at"])
    except Exception as exc:
        logger.warning("Contribution email send unsuccessful: %s", type(exc).__name__)
        DonationContribution.objects.filter(pk=pk).update(receipt_error="email_delivery_failed")


def process_donation_notification(
    payload: Mapping[str, str],
    *,
    gateway: PayFastVerificationGateway,
) -> NotificationResult:
    ref = str(payload.get("m_payment_id", "")).strip()
    provider_ref = str(payload.get("pf_payment_id", "")).strip()
    gateway_status = str(payload.get("payment_status", "")).strip().upper()
    pending = DonationContribution.Status.PENDING
    if (
        not ref.startswith("DON-")
        or not provider_ref
        or gateway_status not in {"PENDING", "COMPLETE", "FAILED", "CANCELLED"}
    ):
        return NotificationResult(False, pending, reason="invalid_donation_callback")
    try:
        donation = DonationContribution.objects.get(reference=ref)
    except DonationContribution.DoesNotExist:
        return NotificationResult(False, pending, reason="unknown_donation")

    if (
        donation.status != DonationContribution.Status.PAID
        and (timezone.now() - donation.created_at).total_seconds() > 7 * 86400
    ):
        return NotificationResult(False, donation.status, reason="callback_window_expired")
    try:
        verified = gateway.verify_notification(payload)
    except (TimeoutError, ConnectionError, OSError):
        return NotificationResult(False, donation.status, reason="provider_verification_unavailable", retryable=True)
    if not verified:
        return NotificationResult(False, donation.status, reason="unverified_notification")

    try:
        amount = Decimal(str(payload.get("amount_gross", "")))
    except (InvalidOperation, ValueError):
        return NotificationResult(False, donation.status, reason="invalid_amount")
    if (
        amount != donation.amount
        or str(payload.get("custom_str1", "")) != donation.reference
        or str(payload.get("custom_str2", "")) != donation.purpose
    ):
        return NotificationResult(False, donation.status, reason="mismatched_donation_details")

    states = {
        "PENDING": DonationContribution.Status.PENDING,
        "COMPLETE": DonationContribution.Status.PAID,
        "FAILED": DonationContribution.Status.FAILED,
        "CANCELLED": DonationContribution.Status.CANCELLED,
    }
    target = states[gateway_status]
    try:
        with transaction.atomic():
            locked = DonationContribution.objects.select_for_update().get(pk=donation.pk)
            if (
                locked.provider_reference and locked.provider_reference != provider_ref
            ) or DonationContribution.objects.filter(provider_reference=provider_ref).exclude(pk=locked.pk).exists():
                return NotificationResult(False, locked.status, reason="provider_reference_replay")
            if locked.status == DonationContribution.Status.PAID:
                if target != DonationContribution.Status.PAID:
                    return NotificationResult(False, locked.status, reason="paid_is_immutable")
                return NotificationResult(True, locked.status, duplicate=True)
            if (
                locked.status in (DonationContribution.Status.FAILED, DonationContribution.Status.CANCELLED)
                and target != locked.status
            ):
                # A late verified payment must go to manual reconciliation.
                return NotificationResult(False, locked.status, reason="final_status_requires_reconciliation")
            locked.provider_reference = provider_ref
            locked.gateway_verified_at = timezone.now()
            locked.last_callback_status = gateway_status
            locked.status = target
            if target == DonationContribution.Status.PAID:
                locked.paid_at = timezone.now()
                transaction.on_commit(partial(_send_donation_acknowledgement, locked.pk))
            locked.save(
                update_fields=[
                    "provider_reference",
                    "gateway_verified_at",
                    "last_callback_status",
                    "status",
                    "paid_at",
                    "updated_at",
                ]
            )
    except IntegrityError:
        return NotificationResult(False, pending, reason="provider_reference_replay")
    return NotificationResult(True, target)
