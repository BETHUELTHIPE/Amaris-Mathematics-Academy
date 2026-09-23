from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import partial
from typing import Protocol
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

from django.db import transaction
from django.utils import timezone

from content.metrics import observe_payment_webhook
from content.models import Course, Enrollment, Payment, StudentRecord
from content.payment_models import Invoice, NotificationOutbox, PaymentWebhookEvent, ServiceTicket

PAYFAST_SANDBOX_URL = "https://sandbox.payfast.co.za/eng/process"
PAYFAST_LIVE_URL = "https://www.payfast.co.za/eng/process"
PAYFAST_SANDBOX_VALIDATE_URL = "https://sandbox.payfast.co.za/eng/query/validate"
PAYFAST_LIVE_VALIDATE_URL = "https://www.payfast.co.za/eng/query/validate"
PAYFAST_SANDBOX_MERCHANT_ID = "10000100"
PAYFAST_SANDBOX_MERCHANT_KEY = "46f0cd694581a"
PAYFAST_SANDBOX_PASSPHRASE = "jt7NOE43FZPn"
PAYMENT_CANCELLED = "cancelled"
PAYMENT_WEBHOOK_MAX_AGE_HOURS = int(os.getenv("PAYMENT_WEBHOOK_MAX_AGE_HOURS", "168"))
logger = logging.getLogger(__name__)


class PaymentSecurityError(ValueError):
    """Raised when a request conflicts with server-owned payment facts."""


class PayFastVerificationGateway(Protocol):
    def verify_notification(self, payload: Mapping[str, str]) -> bool:
        """Return True only after server-side PayFast verification succeeds."""


@dataclass(frozen=True)
class CheckoutSession:
    payment_reference: str
    gateway_url: str
    fields: dict[str, str]


@dataclass(frozen=True)
class NotificationResult:
    accepted: bool
    payment_status: str
    reason: str = ""
    retryable: bool = False
    duplicate: bool = False


def _payfast_mode() -> str:
    mode = os.getenv("PAYFAST_MODE", "sandbox").strip().lower()
    if mode not in {"sandbox", "live"}:
        raise PaymentSecurityError("PAYFAST_MODE must be sandbox or live.")
    return mode


def _payfast_credentials() -> tuple[str, str, str]:
    mode = _payfast_mode()
    if mode == "sandbox":
        merchant_id = os.getenv("PAYFAST_MERCHANT_ID", PAYFAST_SANDBOX_MERCHANT_ID).strip()
        merchant_key = os.getenv("PAYFAST_MERCHANT_KEY", PAYFAST_SANDBOX_MERCHANT_KEY).strip()
        passphrase = os.getenv("PAYFAST_PASSPHRASE", PAYFAST_SANDBOX_PASSPHRASE).strip()
    else:
        merchant_id = os.getenv("PAYFAST_MERCHANT_ID", "").strip()
        merchant_key = os.getenv("PAYFAST_MERCHANT_KEY", "").strip()
        passphrase = os.getenv("PAYFAST_PASSPHRASE", "").strip()
        if not merchant_id or not merchant_key:
            raise PaymentSecurityError("Live PayFast merchant credentials are not configured.")
    return merchant_id, merchant_key, passphrase


def _signature_parameter_string(fields: Mapping[str, str], passphrase: str = "") -> str:
    pairs: list[str] = []
    for key, raw_value in fields.items():
        if key == "signature":
            continue
        value = str(raw_value).strip()
        if value:
            pairs.append(f"{key}={quote_plus(value)}")
    if passphrase:
        pairs.append(f"passphrase={quote_plus(passphrase.strip())}")
    return "&".join(pairs)


def generate_payfast_signature(fields: Mapping[str, str], passphrase: str = "") -> str:
    return hashlib.md5(_signature_parameter_string(fields, passphrase).encode("utf-8")).hexdigest()


def create_checkout(*, student: StudentRecord, course: Course, idempotency_key: str) -> CheckoutSession:
    """Create a server-priced, signed PayFast checkout without granting access."""

    key = idempotency_key.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", key):
        raise PaymentSecurityError("Invalid checkout idempotency key.")
    if not student.is_active:
        raise PaymentSecurityError("Inactive students cannot create checkout sessions.")
    if course.status != Course.Status.PUBLISHED or not course.is_published:
        raise PaymentSecurityError("Only published courses can be purchased.")

    reference = f"PF-{key}"
    with transaction.atomic():
        payment, created = Payment.objects.get_or_create(
            reference=reference,
            defaults={
                "student": student,
                "course": course,
                "provider": Payment.Provider.PAYFAST,
                "amount": course.price,
                "currency": "ZAR",
                "status": Payment.Status.PENDING,
            },
        )
        if not created:
            expected = (
                payment.student_id == student.pk
                and payment.course_id == course.pk
                and payment.provider == Payment.Provider.PAYFAST
                and payment.amount == course.price
                and payment.currency == "ZAR"
            )
            if not expected:
                raise PaymentSecurityError("Checkout idempotency key is already bound to a different purchase.")

    merchant_id, merchant_key, passphrase = _payfast_credentials()
    mode = _payfast_mode()
    site_url = os.getenv("PUBLIC_SITE_URL", "https://amaris-mathematics-academy.bethuelthipe.chatgpt.site").rstrip("/")
    api_url = os.getenv("PUBLIC_API_URL", "").rstrip("/")
    return_url = os.getenv("PAYFAST_RETURN_URL", f"{site_url}/payments/pending").strip()
    cancel_url = os.getenv("PAYFAST_CANCEL_URL", f"{site_url}/payments/cancelled").strip()
    notify_url = os.getenv("PAYFAST_NOTIFY_URL", f"{api_url}/api/v1/payfast/itn/" if api_url else "").strip()

    fields = {
        "merchant_id": merchant_id,
        "merchant_key": merchant_key,
        "return_url": f"{return_url}?reference={payment.reference}",
        "cancel_url": f"{cancel_url}?reference={payment.reference}",
        "notify_url": notify_url,
        "name_first": student.first_name[:100],
        "name_last": student.last_name[:100],
        "email_address": student.email[:100],
        "m_payment_id": payment.reference,
        "amount": f"{payment.amount:.2f}",
        "item_name": course.title[:100],
        "custom_str1": str(student.supabase_user_id),
        "custom_str2": course.slug,
    }
    fields = {key: value for key, value in fields.items() if value != ""}
    fields["signature"] = generate_payfast_signature(fields, passphrase)

    return CheckoutSession(
        payment_reference=payment.reference,
        gateway_url=PAYFAST_SANDBOX_URL if mode == "sandbox" else PAYFAST_LIVE_URL,
        fields=fields,
    )


class HttpPayFastVerificationGateway:
    """Validate PayFast ITN signatures and confirm the payload with PayFast."""

    def verify_notification(self, payload: Mapping[str, str]) -> bool:
        _, _, passphrase = _payfast_credentials()
        supplied_signature = str(payload.get("signature", "")).strip().lower()
        if not supplied_signature:
            return False
        expected_signature = generate_payfast_signature(payload, passphrase)
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return False

        encoded = urlencode(
            [(str(key), str(value)) for key, value in payload.items() if key != "signature" and str(value) != ""]
        ).encode("utf-8")
        validate_url = PAYFAST_SANDBOX_VALIDATE_URL if _payfast_mode() == "sandbox" else PAYFAST_LIVE_VALIDATE_URL
        request = Request(
            validate_url,
            data=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "text/plain"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=float(os.getenv("PAYFAST_VERIFY_TIMEOUT_SECONDS", "8"))) as response:
                return response.read().decode("utf-8").strip() == "VALID"
        except TimeoutError:
            raise
        except OSError as exc:
            raise ConnectionError("PayFast validation request failed.") from exc


def authoritative_payment_status(reference: str) -> str:
    """Return persisted backend state; browser redirects never change it."""

    return Payment.objects.only("status").get(reference=reference).status


def _payload_hash(payload: Mapping[str, str]) -> str:
    safe_payload = {str(key): str(value) for key, value in payload.items() if str(key).lower() != "signature"}
    encoded = json.dumps(safe_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sanitized_payload(payload: Mapping[str, str]) -> dict[str, str]:
    allowed = ("m_payment_id", "pf_payment_id", "payment_status", "amount_gross", "custom_str1", "custom_str2")
    return {key: str(payload.get(key, "")) for key in allowed}


def _reject_event(event: PaymentWebhookEvent, code: str, *, verified: bool = False) -> NotificationResult:
    event.state = PaymentWebhookEvent.State.REJECTED
    event.last_error_code = code[:80]
    if verified:
        event.verified_at = timezone.now()
    event.save(update_fields=["state", "last_error_code", "verified_at", "updated_at"])
    return NotificationResult(False, Payment.Status.PENDING, reason=code)


def _mark_retryable(event: PaymentWebhookEvent, code: str) -> NotificationResult:
    event.state = PaymentWebhookEvent.State.RETRYABLE
    event.last_error_code = code[:80]
    event.save(update_fields=["state", "last_error_code", "updated_at"])
    return NotificationResult(False, Payment.Status.PENDING, reason=code, retryable=True)


def _fulfill_verified_payment(payment: Payment) -> None:
    enrollment, _ = Enrollment.objects.select_for_update().get_or_create(
        student=payment.student,
        course=payment.course,
        defaults={"status": Enrollment.Status.ACTIVE},
    )
    if enrollment.status not in {Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED}:
        enrollment.status = Enrollment.Status.ACTIVE
        enrollment.save(update_fields=["status", "updated_at"])

    if payment.enrollment_id != enrollment.pk:
        payment.enrollment = enrollment
        payment.save(update_fields=["enrollment", "updated_at"])

    invoice, invoice_created = Invoice.objects.get_or_create(
        payment=payment,
        defaults={
            "invoice_number": f"INV-{payment.reference}",
            "student": payment.student,
            "course": payment.course,
            "amount": payment.amount,
            "currency": payment.currency,
            "issued_at": payment.paid_at or timezone.now(),
        },
    )
    if (
        invoice.student_id != payment.student_id
        or invoice.course_id != payment.course_id
        or invoice.amount != payment.amount
        or invoice.currency != payment.currency
    ):
        raise PaymentSecurityError("Existing invoice does not match the verified payment.")

    if invoice_created or not invoice.pdf_storage_path:
        transaction.on_commit(partial(_queue_invoice_archive, invoice.pk))

    ticket, _ = ServiceTicket.objects.get_or_create(
        payment=payment,
        defaults={
            "enrollment": enrollment,
            "ticket_number": f"TKT-{payment.reference}",
            "status": ServiceTicket.Status.FULFILLED,
        },
    )
    if ticket.enrollment_id != enrollment.pk:
        raise PaymentSecurityError("Existing service ticket does not match the verified enrollment.")

    NotificationOutbox.objects.get_or_create(
        payment=payment,
        defaults={
            "event_type": "payment_success",
            "destination": payment.student.email,
            "status": NotificationOutbox.Status.QUEUED,
            "payload": {
                "payment_reference": payment.reference,
                "invoice_number": invoice.invoice_number,
                "ticket_number": ticket.ticket_number,
                "course": payment.course.title,
            },
        },
    )


@observe_payment_webhook("payfast")
def process_payfast_notification(
    payload: Mapping[str, str],
    *,
    gateway: PayFastVerificationGateway,
) -> NotificationResult:
    """Verify and process one PayFast ITN using backend-owned purchase facts.

    This is the only path in the payment service that can mark a payment paid
    and activate a service. A browser redirect or client-supplied success flag
    is deliberately insufficient. Unsettled checkout sessions also have a
    bounded callback acceptance window so very old references cannot be replayed.
    """

    local_reference = str(payload.get("m_payment_id", "")).strip()
    provider_reference = str(payload.get("pf_payment_id", "")).strip()
    gateway_status = str(payload.get("payment_status", "")).strip().upper()
    if not local_reference or not provider_reference or not gateway_status:
        return NotificationResult(False, Payment.Status.PENDING, reason="missing_required_fields")

    try:
        payment = Payment.objects.select_related("student", "course").get(reference=local_reference)
    except Payment.DoesNotExist:
        return NotificationResult(False, Payment.Status.PENDING, reason="unknown_payment")

    event, _ = PaymentWebhookEvent.objects.get_or_create(
        provider=Payment.Provider.PAYFAST,
        provider_reference=provider_reference,
        payment_status=gateway_status,
        defaults={"local_reference": local_reference},
    )
    event.attempts += 1
    event.local_reference = local_reference
    event.payload_hash = _payload_hash(payload)
    event.save(update_fields=["attempts", "local_reference", "payload_hash", "updated_at"])

    if event.state == PaymentWebhookEvent.State.PROCESSED:
        if event.payment_id == payment.pk:
            return NotificationResult(True, payment.status, reason="duplicate_callback", duplicate=True)
        return NotificationResult(False, payment.status, reason="provider_reference_replay", duplicate=True)

    if payment.status != Payment.Status.PAID:
        callback_age_seconds = max(0.0, (timezone.now() - payment.created_at).total_seconds())
        if callback_age_seconds > PAYMENT_WEBHOOK_MAX_AGE_HOURS * 3600:
            return _reject_event(event, "callback_window_expired")

    try:
        verified = gateway.verify_notification(payload)
    except TimeoutError:
        return _mark_retryable(event, "verification_timeout")
    except (ConnectionError, OSError):
        return _mark_retryable(event, "verification_network_failure")

    if not verified:
        return _reject_event(event, "invalid_callback")

    try:
        callback_amount = Decimal(str(payload.get("amount_gross", "")))
    except (InvalidOperation, ValueError):
        return _reject_event(event, "invalid_amount", verified=True)

    if callback_amount != payment.amount:
        return _reject_event(event, "tampered_amount", verified=True)
    if str(payload.get("custom_str1", "")) != str(payment.student.supabase_user_id):
        return _reject_event(event, "wrong_student", verified=True)
    if str(payload.get("custom_str2", "")) != payment.course.slug:
        return _reject_event(event, "wrong_service", verified=True)
    if payment.provider != Payment.Provider.PAYFAST:
        return _reject_event(event, "wrong_provider", verified=True)

    status_map = {
        "PENDING": Payment.Status.PENDING,
        "COMPLETE": Payment.Status.PAID,
        "FAILED": Payment.Status.FAILED,
        "CANCELLED": PAYMENT_CANCELLED,
    }
    target_status = status_map.get(gateway_status)
    if target_status is None:
        return _reject_event(event, "unsupported_payment_status", verified=True)

    with transaction.atomic():
        locked_payment = Payment.objects.select_for_update().select_related("student", "course").get(pk=payment.pk)
        locked_event = PaymentWebhookEvent.objects.select_for_update().get(pk=event.pk)

        if locked_event.state == PaymentWebhookEvent.State.PROCESSED:
            return NotificationResult(True, locked_payment.status, reason="duplicate_callback", duplicate=True)

        if locked_event.payment_id not in (None, locked_payment.pk):
            return _reject_event(locked_event, "provider_reference_replay", verified=True)
        if locked_payment.provider_reference and locked_payment.provider_reference != provider_reference:
            return _reject_event(locked_event, "provider_reference_mismatch", verified=True)

        if locked_payment.status == Payment.Status.PAID and locked_payment.gateway_verified_at:
            if target_status != Payment.Status.PAID:
                return _reject_event(locked_event, "paid_payment_is_immutable", verified=True)
        else:
            locked_payment.provider_reference = provider_reference
            locked_payment.status = target_status
            locked_payment.gateway_verified_at = timezone.now()
            locked_payment.verification_source = "payfast_server_verification"
            locked_payment.raw_response = _sanitized_payload(payload)
            if target_status == Payment.Status.PAID:
                locked_payment.paid_at = timezone.now()
            locked_payment.save(
                update_fields=[
                    "provider_reference",
                    "status",
                    "gateway_verified_at",
                    "verification_source",
                    "raw_response",
                    "paid_at",
                    "updated_at",
                ]
            )

        if target_status == Payment.Status.PAID:
            _fulfill_verified_payment(locked_payment)

        now = timezone.now()
        locked_event.payment = locked_payment
        locked_event.state = PaymentWebhookEvent.State.PROCESSED
        locked_event.last_error_code = ""
        locked_event.verified_at = now
        locked_event.processed_at = now
        locked_event.save(
            update_fields=[
                "payment",
                "state",
                "last_error_code",
                "verified_at",
                "processed_at",
                "updated_at",
            ]
        )

    return NotificationResult(True, target_status)


def _queue_invoice_archive(invoice_id: int) -> None:
    """Archive after a verified payment even when the broker is unavailable."""

    from content.services.invoices import archive_invoice_pdf, mark_invoice_archive_failure
    from content.tasks import archive_invoice_pdf_task

    try:
        archive_invoice_pdf_task.delay(invoice_id)
    except Exception:
        logger.exception("invoice_archive_enqueue_failed", extra={"invoice_id": invoice_id})
        try:
            archive_invoice_pdf(invoice_id)
        except Exception as exc:
            mark_invoice_archive_failure(invoice_id, exc)
            logger.exception("invoice_archive_fallback_failed", extra={"invoice_id": invoice_id})
