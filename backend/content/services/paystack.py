"""Hosted checkout and transaction verification for Paystack live-class payments."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .payments import PaymentSecurityError

PAYSTACK_API = "https://api.paystack.co"
BOOKING_REFERENCE = re.compile(r"LCB-PS-[a-f0-9]{64}")
SIGNATURE = re.compile(r"[0-9a-f]{128}")


class PaystackUnavailable(PaymentSecurityError):
    """The provider request can be retried."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def mode() -> str:
    return os.getenv("PAYSTACK_MODE", "test").strip().lower()


def _configured_key() -> str:
    key = os.getenv("PAYSTACK_SECRET_KEY", "").strip()
    return key if mode() in {"test", "live"} and key.startswith(f"sk_{mode()}_") else ""


def _site_origin() -> str:
    url = os.getenv("PUBLIC_SITE_URL", "").rstrip("/")
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme == "https"
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            and not parsed.path
            and not parsed.query
            and not parsed.fragment
        ):
            return url
    except ValueError:
        pass
    return ""


def checkout_enabled() -> bool:
    return (
        os.getenv("PAYSTACK_ENABLED", "false").strip().lower() == "true"
        and bool(_configured_key())
        and bool(_site_origin())
    )


def booking_reference(idempotency_key: str) -> str:
    return "LCB-PS-" + hashlib.sha256(idempotency_key.encode()).hexdigest()


def _request(path: str, *, payload: dict | None = None) -> dict:
    key = _configured_key()
    if not key:
        raise PaystackUnavailable("Paystack is temporarily unavailable.")
    request = Request(
        f"{PAYSTACK_API}{path}",
        data=json.dumps(payload).encode() if payload is not None else None,
        method="POST" if payload is not None else "GET",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with build_opener(_NoRedirect()).open(request, timeout=6) as response:
            data = json.loads(response.read(1024 * 1024))
    except HTTPError as exc:
        if exc.code == 429 or exc.code >= 500:
            raise PaystackUnavailable("Paystack is temporarily unavailable.") from exc
        raise PaymentSecurityError("Paystack could not open or verify this payment.") from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise PaystackUnavailable("Paystack is temporarily unavailable.") from exc
    if not isinstance(data, dict) or data.get("status") is not True or not isinstance(data.get("data"), dict):
        raise PaymentSecurityError("Paystack did not confirm the transaction request.")
    return data["data"]


def is_checkout_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.netloc == "checkout.paystack.com" and len(parsed.path) > 1


def initialize(*, email: str, amount: Decimal, reference: str) -> str:
    if not checkout_enabled():
        raise PaymentSecurityError("Paystack checkout is unavailable.")
    cents = int(amount * 100)
    if cents <= 0 or Decimal(cents) / 100 != amount:
        raise PaymentSecurityError("Invalid ZAR payment amount.")
    data = _request(
        "/transaction/initialize",
        payload={
            "email": email,
            "amount": cents,
            "currency": "ZAR",
            "reference": reference,
            "callback_url": f"{_site_origin()}/book-online-live-class/confirmation?reference={quote(reference)}",
        },
    )
    url = data.get("authorization_url")
    if not isinstance(url, str) or len(url) > 500 or not is_checkout_url(url) or data.get("reference") != reference:
        raise PaymentSecurityError("Paystack returned an invalid checkout.")
    return url


def verified_payment(reference: str) -> tuple[int, str]:
    if not BOOKING_REFERENCE.fullmatch(reference):
        raise PaymentSecurityError("Invalid Paystack booking reference.")
    data = _request(f"/transaction/verify/{reference}")
    if data.get("reference") != reference or data.get("status") != "success":
        raise PaymentSecurityError("Paystack has not verified this payment.")
    if data.get("domain") != mode() or data.get("currency") != "ZAR":
        raise PaymentSecurityError("Unexpected Paystack currency or payment mode.")
    amount = data.get("amount")
    transaction_id = data.get("id")
    if type(amount) is not int or amount <= 0 or type(transaction_id) is not int or transaction_id <= 0:
        raise PaymentSecurityError("Invalid Paystack amount or transaction ID.")
    return amount, str(transaction_id)


def valid_webhook(body: bytes, modern: str, legacy: str) -> bool:
    if modern:
        secret = os.getenv("PAYSTACK_WEBHOOK_SECRET", "").strip()
        pieces = [part.strip() for part in modern.split(",")]
        timestamps = [part[2:] for part in pieces if part.startswith("t=")]
        if (
            not secret.startswith("whsec_")
            or len(timestamps) != 1
            or not re.fullmatch(r"[0-9]{1,12}", timestamps[0])
            or abs(time.time() - int(timestamps[0])) > 300
        ):
            return False
        expected = hmac.new(secret.encode(), timestamps[0].encode() + b"." + body, hashlib.sha512).hexdigest()
        for part in pieces:
            if part.startswith("v1="):
                key_id, _, signature = part[3:].partition(":")
                if (
                    key_id.startswith("whk_")
                    and SIGNATURE.fullmatch(signature)
                    and hmac.compare_digest(signature, expected)
                ):
                    return True
        return False

    secret = _configured_key()
    if not secret or not SIGNATURE.fullmatch(legacy):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(legacy, expected)
