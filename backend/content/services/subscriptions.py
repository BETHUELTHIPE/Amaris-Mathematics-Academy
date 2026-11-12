"""One upfront PayFast payment for one curriculum and a calendar-month term."""

import calendar
import hashlib
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from content.models import Course, Enrollment, StudentRecord
from content.services.invoice_document import InvoiceDocument, InvoiceLine, render_document
from content.services.payments import (
    PAYFAST_LIVE_URL,
    PAYFAST_SANDBOX_URL,
    NotificationResult,
    PaymentSecurityError,
    _payfast_credentials,
    _payfast_mode,
    generate_payfast_signature,
)
from content.subscription_models import CurriculumSubscription

PRICES = {4: Decimal("3800.00"), 8: Decimal("7600.00")}
CURRICULUM_ALIASES = {
    "caps": {"CAPS"},
    "ieb": {"IEB"},
    "nated": {"NATED", "TVET NATED"},
    "ncv": {"NCV", "NC(V)", "TVET NC(V)"},
    "university": {"Higher Education", "University", "UNISA", "University / UNISA"},
}


def add_calendar_months(value, months):
    offset = value.year * 12 + value.month - 1 + months
    year, month = divmod(offset, 12)
    month += 1
    return value.replace(year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1]))


def live_subscriptions(student):
    now = timezone.now()
    return CurriculumSubscription.objects.filter(
        student=student,
        status="paid",
        gateway_verified_at__isnull=False,
        gateway_mode=_payfast_mode(),
        starts_at__lte=now,
        ends_at__gt=now,
    )


def accessible_enrollments():
    now = timezone.now()
    matching_curriculum = Q(pk__isnull=True)
    for curriculum, labels in CURRICULUM_ALIASES.items():
        for label in labels:
            matching_curriculum |= Q(subscription_access__curriculum=curriculum, course__curriculum__iexact=label)
    return Q(subscription_access__isnull=True) | (
        matching_curriculum
        & Q(
            subscription_access__status="paid",
            subscription_access__gateway_verified_at__isnull=False,
            subscription_access__gateway_mode=_payfast_mode(),
            subscription_access__starts_at__lte=now,
            subscription_access__ends_at__gt=now,
        )
    )


def refresh_subscription_courses(student, course=None):
    """Materialize progress rows without turning expiring access into lifetime access."""
    for subscription in live_subscriptions(student):
        matches = Q()
        for label in CURRICULUM_ALIASES[subscription.curriculum]:
            matches |= Q(curriculum__iexact=label)
        courses = Course.objects.filter(matches, is_published=True, status="published").filter(
            Q(publish_at__isnull=True) | Q(publish_at__lte=timezone.now())
        )
        if course is not None:
            courses = courses.filter(slug=course)
        for item in courses:
            enrollment, created = Enrollment.objects.get_or_create(
                student=student,
                course=item,
                defaults={"status": "active", "subscription_access": subscription},
            )
            # Never override an administrator's cancellation or a separately purchased course.
            if (
                not created
                and enrollment.status != "cancelled"
                and (enrollment.subscription_access_id or enrollment.status == "pending")
            ):
                enrollment.subscription_access = subscription
                enrollment.status = "active"
                enrollment.save(update_fields=["subscription_access", "status", "updated_at"])


def create_subscription_checkout(*, student, curriculum, months, idempotency_key):
    if not getattr(settings, "COURSE_SUBSCRIPTIONS_ENABLED", False):
        raise PaymentSecurityError("Subscription checkout is not available yet.")
    if curriculum not in CURRICULUM_ALIASES or months not in PRICES:
        raise PaymentSecurityError("Choose a curriculum and a four- or eight-month plan.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", idempotency_key) or not student.is_active:
        raise PaymentSecurityError("Invalid subscription checkout.")
    merchant, key, passphrase = _payfast_credentials()
    mode = _payfast_mode()
    with transaction.atomic():
        StudentRecord.objects.select_for_update().get(pk=student.pk)
        reference = "SUB-" + hashlib.sha256(f"{student.pk}:{idempotency_key}".encode()).hexdigest()[:32].upper()
        item = CurriculumSubscription.objects.filter(reference=reference).first()
        if item and (item.curriculum != curriculum or item.months != months or item.gateway_mode != mode):
            raise PaymentSecurityError("Checkout key belongs to another subscription.")
        if not item:
            if live_subscriptions(student).filter(curriculum=curriculum).exists():
                raise PaymentSecurityError("You already have an active subscription for this curriculum.")
            # A page refresh reuses the recent unpaid order instead of creating duplicate purchases.
            item = CurriculumSubscription.objects.filter(
                student=student,
                curriculum=curriculum,
                months=months,
                gateway_mode=mode,
                status="pending",
                created_at__gte=timezone.now() - timedelta(days=1),
            ).first()
            if not item:
                item = CurriculumSubscription.objects.create(
                    student=student,
                    reference=reference,
                    idempotency_key=idempotency_key,
                    curriculum=curriculum,
                    months=months,
                    amount=PRICES[months],
                    gateway_mode=mode,
                )
    if item.status != "pending":
        raise PaymentSecurityError("This order is already settled; view your subscriptions.")
    site = settings.PUBLIC_SITE_URL.rstrip("/")
    api = getattr(settings, "PUBLIC_API_URL", "").rstrip("/")
    if not api:
        import os

        api = os.getenv("PUBLIC_API_URL", "").rstrip("/")
    if not site.startswith("https://") or not api.startswith("https://"):
        raise PaymentSecurityError("Secure subscription checkout URLs are not configured.")
    fields = {
        "merchant_id": merchant,
        "merchant_key": key,
        "return_url": f"{site}/subscriptions/status?reference={item.reference}",
        "cancel_url": f"{site}/subscriptions/status?reference={item.reference}&cancelled=1",
        "notify_url": f"{api}/api/v1/payfast/itn/",
        "name_first": student.first_name[:100],
        "name_last": student.last_name[:100],
        "email_address": student.email[:100],
        "m_payment_id": item.reference,
        "amount": f"{item.amount:.2f}",
        "item_name": f"{item.get_curriculum_display()} course subscription — {months} months"[:100],
        "custom_str1": str(student.supabase_user_id),
        "custom_str2": f"{curriculum}:{months}",
    }
    fields = {name: value for name, value in fields.items() if value}
    fields["signature"] = generate_payfast_signature(fields, passphrase)
    return item, PAYFAST_SANDBOX_URL if mode == "sandbox" else PAYFAST_LIVE_URL, fields


def process_subscription_notification(payload, *, gateway):
    reference = str(payload.get("m_payment_id", ""))
    item = CurriculumSubscription.objects.select_related("student").filter(reference=reference).first()
    if item is None:
        return NotificationResult(False, "pending", reason="Unknown subscription.")
    try:
        merchant, _, _ = _payfast_credentials()
        amount = Decimal(str(payload.get("amount_gross", "")))
        valid = (
            amount.is_finite()
            and amount == item.amount
            and item.currency == "ZAR"
            and item.gateway_mode == _payfast_mode()
            and str(payload.get("merchant_id", "")) == merchant
            and str(payload.get("custom_str1", "")) == str(item.student.supabase_user_id)
            and str(payload.get("custom_str2", "")) == f"{item.curriculum}:{item.months}"
            and bool(re.fullmatch(r"[A-Za-z0-9_-]{1,160}", str(payload.get("pf_payment_id", ""))))
        )
        if not valid or not gateway.verify_notification(payload):
            return NotificationResult(False, "pending", reason="Subscription verification failed.")
    except (InvalidOperation, ValueError):
        return NotificationResult(False, "pending", reason="Invalid subscription payment.")
    except (OSError, TimeoutError):
        return NotificationResult(False, "pending", reason="Payment verification unavailable.", retryable=True)
    with transaction.atomic():
        # Serialize different orders belonging to one student as well as duplicate callbacks.
        StudentRecord.objects.select_for_update().get(pk=item.student_id)
        item = CurriculumSubscription.objects.select_for_update().get(pk=item.pk)
        provider = str(payload["pf_payment_id"])
        if item.provider_reference and item.provider_reference != provider:
            return NotificationResult(False, item.status, reason="Payment reference conflict.")
        if CurriculumSubscription.objects.filter(provider_reference=provider).exclude(pk=item.pk).exists():
            return NotificationResult(False, item.status, reason="Payment reference already used.")
        state = str(payload.get("payment_status", "")).upper()
        if item.status == "refunded":
            return NotificationResult(True, item.status, duplicate=True)
        if state in {"REFUNDED", "REVERSED"}:
            item.status = "refunded"
        elif state == "COMPLETE" and item.status == "pending":
            item.status = "paid"
            item.starts_at = timezone.now()
            item.ends_at = add_calendar_months(item.starts_at, item.months)
        elif state != "COMPLETE":
            return NotificationResult(True, item.status)
        elif item.status == "paid":
            return NotificationResult(True, item.status, duplicate=True)
        item.provider_reference = provider
        item.gateway_verified_at = item.gateway_verified_at or timezone.now()
        item.save(
            update_fields=["status", "starts_at", "ends_at", "provider_reference", "gateway_verified_at", "updated_at"]
        )
    return NotificationResult(True, item.status)


@transaction.atomic
def subscription_invoice(item):
    item = CurriculumSubscription.objects.select_for_update().select_related("student").get(pk=item.pk)
    if item.status != "paid" or item.gateway_verified_at is None:
        raise PaymentSecurityError("A verified subscription payment is required.")
    storage = storages["student_private"]
    key = item.pdf_storage_path
    if not key:
        number = f"INV-{item.reference}"
        data = render_document(
            InvoiceDocument(
                number=number,
                issue_date=timezone.localtime(item.gateway_verified_at).strftime("%d %B %Y"),
                student_name=f"{item.student.first_name} {item.student.last_name}".strip(),
                student_email=item.student.email,
                reference=item.provider_reference or item.reference,
                currency="ZAR",
                lines=(
                    InvoiceLine(
                        description=f"{item.months}-month {item.get_curriculum_display()} course subscription",
                        details=(
                            f"Access: {item.starts_at:%d %B %Y} to {item.ends_at:%d %B %Y}",
                            "Includes 2 x 2-hour one-to-one Zoom sessions per week (4 hours total)",
                            "Published courses in the selected curriculum",
                            "One upfront payment",
                        ),
                        quantity=Decimal("1"),
                        unit_price=item.amount,
                    ),
                ),
                total=item.amount,
            )
        )
        key = storage.save(f"{item.student.supabase_user_id}/subscriptions/{number}.pdf", ContentFile(data))
        item.pdf_storage_path = key
        item.save(update_fields=["pdf_storage_path", "updated_at"])
    return storage.open(key, "rb")
