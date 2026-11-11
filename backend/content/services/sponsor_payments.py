"""Hosted sponsor payments. Browser redirects and unverified payloads never credit funding."""

import hashlib
import hmac
import json
import os
import re
import time
import uuid
from decimal import Decimal, InvalidOperation
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from content.sponsor_models import SponsorContribution

from .payments import (
    PAYFAST_LIVE_URL,
    PAYFAST_SANDBOX_URL,
    HttpPayFastVerificationGateway,
    NotificationResult,
    PaymentSecurityError,
    _payfast_credentials,
    _payfast_mode,
    build_payfast_notify_url,
    generate_payfast_signature,
)


class SponsorGatewayUnavailable(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _flag(name):
    return os.getenv(name, "false").strip().lower() in {"true", "1", "yes"}


def _mode(provider):
    if provider == "payfast":
        return "test" if _payfast_mode() == "sandbox" else "live"
    mode = os.getenv("PAYSTACK_MODE", "test").strip().lower()
    if mode not in {"test", "live"}:
        raise PaymentSecurityError("Invalid payment environment.")
    return mode


def _paystack_secret():
    mode = _mode("paystack")
    secret = os.getenv("PAYSTACK_SECRET_KEY", "").strip()
    if not secret.startswith(f"sk_{mode}_"):
        raise SponsorGatewayUnavailable("Paystack is temporarily unavailable.")
    return secret


def _public_urls():
    site, api = settings.PUBLIC_SITE_URL.rstrip("/"), settings.PUBLIC_API_URL.rstrip("/")
    for value in (site, api):
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise SponsorGatewayUnavailable("Online sponsorship is temporarily unavailable.")
    return site, api


def payment_options():
    options = []
    for provider, label in (("payfast", "PayFast"), ("paystack", "Paystack")):
        available, mode = False, "test"
        try:
            mode = _mode(provider)
            _public_urls()
            if provider == "payfast":
                merchant_id, merchant_key, _ = _payfast_credentials()
                if not merchant_id or not merchant_key:
                    raise SponsorGatewayUnavailable("PayFast is temporarily unavailable.")
            else:
                _paystack_secret()
                if not os.getenv("PAYSTACK_WEBHOOK_SECRET", "").startswith("whsec_") and not _flag(
                    "PAYSTACK_ALLOW_LEGACY_WEBHOOK_SIGNATURE"
                ):
                    raise SponsorGatewayUnavailable("Paystack verification is not configured.")
            available = _flag("SPONSOR_PAYMENTS_ENABLED") and _flag(f"SPONSOR_{provider.upper()}_ENABLED")
        except (PaymentSecurityError, SponsorGatewayUnavailable):
            pass
        options.append({"provider": provider, "label": label, "available": available, "mode": mode})
    return options


def _paystack_request(path, *, payload=None):
    request = Request(
        "https://api.paystack.co" + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        method="POST" if payload is not None else "GET",
        headers={
            "Authorization": "Bearer " + _paystack_secret(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with build_opener(NoRedirect()).open(request, timeout=8) as response:
            body = response.read(1_000_001)
        if len(body) > 1_000_000:
            raise ValueError("oversized_response")
        result = json.loads(body)
        if not isinstance(result, dict) or result.get("status") is not True or not isinstance(result.get("data"), dict):
            raise ValueError("invalid_response")
        return result["data"]
    except (OSError, ValueError) as exc:
        raise SponsorGatewayUnavailable("The payment gateway is temporarily unavailable.") from exc


def _payfast_session(contribution):
    site, api = _public_urls()
    merchant_id, merchant_key, passphrase = _payfast_credentials()
    if _mode("payfast") != contribution.payment_mode:
        raise PaymentSecurityError("The checkout environment has changed. Contact Amaris.")
    return_url = f"{site}/sponsor/payments/{contribution.reference}"
    fields = {
        "merchant_id": merchant_id,
        "merchant_key": merchant_key,
        "return_url": return_url,
        "cancel_url": return_url + "?cancelled=1",
        "notify_url": build_payfast_notify_url(api),
        "email_address": contribution.payment_email,
        "m_payment_id": contribution.reference,
        "amount": f"{contribution.amount:.2f}",
        "item_name": "Amaris education sponsorship",
        "custom_str1": str(contribution.sponsor_id),
    }
    fields["signature"] = generate_payfast_signature(fields, passphrase)
    return {
        "gateway_url": PAYFAST_SANDBOX_URL if contribution.payment_mode == "test" else PAYFAST_LIVE_URL,
        "fields": fields,
    }


def create_checkout(*, sponsor, email, amount, provider, idempotency_key):
    if provider not in {"payfast", "paystack"} or not any(
        item["provider"] == provider and item["available"] for item in payment_options()
    ):
        raise SponsorGatewayUnavailable("The selected payment option is temporarily unavailable.")
    if (
        not sponsor.is_active
        or not email
        or not amount.is_finite()
        or not Decimal("10.00") <= amount <= Decimal("1000000.00")
        or amount != amount.quantize(Decimal("0.01"))
    ):
        raise PaymentSecurityError("Enter a contribution from R10 to R1,000,000 with at most two decimal places.")
    try:
        nonce = str(uuid.UUID(str(idempotency_key)))
    except (ValueError, TypeError) as exc:
        raise PaymentSecurityError("Invalid checkout request.") from exc
    key = hashlib.sha256(f"{sponsor.pk}:{nonce}".encode()).hexdigest()
    mode = _mode(provider)
    # Commit the local reference before contacting a remote initializer.
    contribution, _ = SponsorContribution.objects.get_or_create(
        payment_idempotency_key=key,
        defaults={
            "sponsor": sponsor,
            "reference": "SC-" + uuid.uuid4().hex,
            "amount": amount,
            "provider": provider,
            "payment_mode": mode,
            "payment_email": email,
            "status": "pending",
            "description": "Education sponsorship",
        },
    )
    with transaction.atomic():
        contribution = SponsorContribution.objects.select_for_update().get(pk=contribution.pk)
        if (contribution.sponsor_id, contribution.amount, contribution.provider, contribution.payment_mode) != (
            sponsor.pk,
            amount,
            provider,
            mode,
        ):
            raise PaymentSecurityError("This checkout request is already bound to another contribution.")
        if contribution.status != "pending":
            raise PaymentSecurityError("This contribution is no longer awaiting payment.")
        if provider == "payfast":
            session = _payfast_session(contribution)
        elif contribution.checkout_url:
            session = {"gateway_url": contribution.checkout_url, "fields": {}}
        else:
            if contribution.initialization_started_at:
                raise SponsorGatewayUnavailable(
                    "This checkout requires review. Check contribution history before starting another payment."
                )
            contribution.initialization_started_at = timezone.now()
            contribution.save(update_fields=("initialization_started_at", "updated_at"))
            session = None
    if session is None:
        try:
            site, _ = _public_urls()
            data = _paystack_request(
                "/transaction/initialize",
                payload={
                    "email": contribution.payment_email,
                    "amount": int(contribution.amount * 100),
                    "currency": "ZAR",
                    "reference": contribution.reference,
                    "callback_url": f"{site}/sponsor/payments/{contribution.reference}",
                    "metadata": {"purpose": "sponsor_contribution", "sponsor_id": str(sponsor.pk)},
                },
            )
            url = str(data.get("authorization_url", ""))
            parsed = urlsplit(url)
            if (
                parsed.scheme != "https"
                or parsed.netloc != "checkout.paystack.com"
                or not parsed.path.strip("/")
                or parsed.username
                or parsed.password
                or parsed.fragment
                or data.get("reference") != contribution.reference
            ):
                raise PaymentSecurityError("The payment gateway returned an invalid checkout.")
            SponsorContribution.objects.filter(pk=contribution.pk).update(checkout_url=url)
            session = {"gateway_url": url, "fields": {}}
        except (PaymentSecurityError, SponsorGatewayUnavailable):
            SponsorContribution.objects.filter(pk=contribution.pk).update(last_error_code="initialization_review")
            raise
    return {
        "reference": contribution.reference,
        "provider": provider,
        "mode": mode,
        "amount": f"{contribution.amount:.2f}",
        "currency": "ZAR",
        **session,
    }


def _settle(reference, provider, mode, provider_reference, amount, email=None):
    if not provider_reference or len(provider_reference) > 160:
        raise PaymentSecurityError("Missing gateway payment reference.")
    with transaction.atomic():
        contribution = SponsorContribution.objects.select_for_update().get(reference=reference)
        if (contribution.provider, contribution.payment_mode, contribution.amount) != (provider, mode, amount):
            raise PaymentSecurityError("The gateway payment does not match this contribution.")
        if email is not None and contribution.payment_email.casefold() != email.casefold():
            raise PaymentSecurityError("The payer does not match this contribution.")
        if contribution.provider_reference:
            if contribution.provider_reference != provider_reference:
                raise PaymentSecurityError("This contribution has a different gateway payment.")
            return contribution.status
        if contribution.status == "refunded":
            raise PaymentSecurityError("This contribution requires manual review.")
        if (
            SponsorContribution.objects.exclude(pk=contribution.pk)
            .filter(provider=provider, payment_mode=mode, provider_reference=provider_reference)
            .exists()
        ):
            raise PaymentSecurityError("This gateway payment is already recorded.")
        contribution.status = "received"
        contribution.provider_reference = provider_reference
        contribution.gateway_verified_at = timezone.now()
        contribution.received_at = timezone.now()
        contribution.last_error_code = ""
        contribution.save(
            update_fields=(
                "status",
                "provider_reference",
                "gateway_verified_at",
                "received_at",
                "last_error_code",
                "updated_at",
            )
        )
        return contribution.status


def process_payfast_sponsor_notification(payload, *, gateway=None):
    reference = str(payload.get("m_payment_id", ""))
    try:
        contribution = SponsorContribution.objects.get(reference=reference, provider="payfast")
        if contribution.payment_mode != _mode("payfast"):
            raise PaymentSecurityError("Payment environment mismatch.")
        verifier = gateway or HttpPayFastVerificationGateway()
        if not verifier.verify_notification(payload):
            raise PaymentSecurityError("Payment verification failed.")
        amount = Decimal(str(payload.get("amount_gross", "")))
        if not amount.is_finite() or amount != contribution.amount:
            raise PaymentSecurityError("Payment amount mismatch.")
        if str(payload.get("payment_status", "")).upper() != "COMPLETE":
            # Delayed failure/cancellation messages must not undo received funds.
            if str(payload.get("payment_status", "")).upper() in {"FAILED", "CANCELLED"}:
                SponsorContribution.objects.filter(pk=contribution.pk, status="pending").update(status="failed")
                contribution.refresh_from_db()
            return NotificationResult(True, contribution.status)
        status = _settle(reference, "payfast", contribution.payment_mode, str(payload.get("pf_payment_id", "")), amount)
        return NotificationResult(True, status)
    except (SponsorContribution.DoesNotExist, PaymentSecurityError, InvalidOperation):
        return NotificationResult(False, "rejected", "Sponsor payment verification failed.")
    except OSError:
        return NotificationResult(False, "pending", "Payment verification is temporarily unavailable.", retryable=True)


def verify_paystack(reference):
    contribution = SponsorContribution.objects.get(reference=reference, provider="paystack")
    if contribution.payment_mode != _mode("paystack"):
        raise PaymentSecurityError("Payment environment mismatch.")
    data = _paystack_request("/transaction/verify/" + quote(reference, safe=""))
    actual = data.get("amount")
    provider_id = str(data.get("id", ""))
    if (
        data.get("reference") != reference
        or data.get("status") != "success"
        or data.get("currency") != "ZAR"
        or data.get("domain") != contribution.payment_mode
        or isinstance(actual, bool)
        or not isinstance(actual, int)
        or actual <= 0
        or not provider_id.isdigit()
    ):
        raise PaymentSecurityError("The gateway has not verified this contribution.")
    customer = data.get("customer")
    email = customer.get("email") if isinstance(customer, dict) else None
    if not isinstance(email, str) or not email:
        raise PaymentSecurityError("The gateway payer is missing.")
    return _settle(reference, "paystack", contribution.payment_mode, provider_id, Decimal(actual) / 100, email)


def valid_paystack_signature(raw_body, headers):
    header = headers.get("Paystack-Signature", "")
    if len(header) > 4096:
        return False
    secrets = [
        value
        for value in (os.getenv("PAYSTACK_WEBHOOK_SECRET", ""), os.getenv("PAYSTACK_WEBHOOK_SECRET_PREVIOUS", ""))
        if value
    ]
    if header or secrets:
        if not header or not secrets:
            return False
        timestamp, signatures = None, []
        for item in header.split(","):
            name, _, value = item.strip().partition("=")
            if name == "t":
                if timestamp is not None or not value.isdigit() or not 1 <= len(value) <= 12:
                    return False
                timestamp = value
            elif name == "v1":
                _, _, signature = value.partition(":")
                if re.fullmatch(r"[0-9a-f]{128}", signature):
                    signatures.append(signature)
        if timestamp is None or abs(time.time() - int(timestamp)) > 300:
            return False
        material = timestamp.encode() + b"." + raw_body
        return any(
            hmac.compare_digest(hmac.new(secret.encode(), material, hashlib.sha512).hexdigest(), signature)
            for secret in secrets
            for signature in signatures
        )
    if not _flag("PAYSTACK_ALLOW_LEGACY_WEBHOOK_SIGNATURE"):
        return False
    supplied = headers.get("X-Paystack-Signature", "")
    return bool(re.fullmatch(r"[0-9a-f]{128}", supplied)) and hmac.compare_digest(
        hmac.new(_paystack_secret().encode(), raw_body, hashlib.sha512).hexdigest(), supplied
    )


def resume_checkout(contribution):
    if contribution.status != "pending" or not any(
        item["provider"] == contribution.provider and item["available"] and item["mode"] == contribution.payment_mode
        for item in payment_options()
    ):
        return None
    if contribution.provider == "payfast":
        return _payfast_session(contribution)
    if contribution.provider == "paystack" and contribution.checkout_url:
        return {"gateway_url": contribution.checkout_url, "fields": {}}
    return None
