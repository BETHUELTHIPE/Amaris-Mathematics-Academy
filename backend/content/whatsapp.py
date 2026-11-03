"""Opt-in WhatsApp booking messages through the Meta Cloud API.

Beat discovers due messages, then a database-backed outbox dispatches them.
Provider acceptance is NOT proof of handset delivery. Indeterminate network
outcomes are never automatically retried, to avoid duplicate WhatsApps.
"""
import json
import logging
import os
import re
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from celery import shared_task
from django.conf import settings
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from .models import LiveClassBooking

logger = logging.getLogger(__name__)
SAST = ZoneInfo("Africa/Johannesburg")
MAX_ATTEMPTS = 3


class WhatsAppPreference(models.Model):
    student = models.OneToOneField(
        "content.StudentRecord",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="whatsapp_preference",
    )
    tutor = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="whatsapp_preference",
    )
    number = models.CharField(max_length=20, help_text="E.164 number, e.g. +27821234567")
    opted_in = models.BooleanField(default=False)
    consent_recorded_at = models.DateTimeField(null=True, blank=True)
    consent_source = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(student__isnull=False, tutor__isnull=True)
                    | models.Q(student__isnull=True, tutor__isnull=False)
                ),
                name="whatsapp_exactly_one_recipient",
            )
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        if bool(self.student_id) == bool(self.tutor_id):
            raise ValidationError("Choose exactly one student or tutor.")
        if not re.fullmatch(r"\+[1-9][0-9]{7,14}", self.number):
            raise ValidationError("Use E.164 format such as +27821234567.")
        if self.opted_in and not self.consent_recorded_at:
            raise ValidationError("Explicit consent time is required.")

    def __str__(self):
        return f"WhatsApp preference #{self.pk}"


class WhatsAppDelivery(models.Model):
    class Kind(models.TextChoices):
        CONFIRMATION = "confirmation", "Booking confirmation"
        REMINDER = "reminder", "30-minute reminder"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENDING = "sending", "Sending (claimed)"
        RETRY = "retry", "Rate-limited; retry scheduled"
        SENT = "sent", "Accepted by provider"
        SKIPPED = "skipped", "Skipped"
        FAILED = "failed", "Failed"
        UNKNOWN = "unknown", "Uncertain; manual review"

    booking = models.ForeignKey(
        LiveClassBooking, related_name="whatsapp_deliveries", on_delete=models.CASCADE
    )
    preference = models.ForeignKey(WhatsAppPreference, on_delete=models.PROTECT)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    slot_start = models.DateTimeField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    provider_id = models.CharField(max_length=128, blank=True)
    receipt_status = models.CharField(max_length=16, blank=True, default="")
    error_code = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["booking", "preference", "kind", "slot_start"],
                name="whatsapp_unique_booking_event",
            )
        ]


class ProviderRejectedError(Exception):
    """An explicit non-retryable error response from Meta."""


class ProviderRateLimitedError(Exception):
    """Meta explicitly rejected the attempt with HTTP 429."""


class DeliveryUncertainError(Exception):
    """The request MAY have been accepted; do not resend automatically."""


def _send_template(number, template, params):
    token = os.getenv("WHATSAPP_CLOUD_TOKEN", "")
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    version = os.getenv("WHATSAPP_GRAPH_API_VERSION", "")
    if not all((token, phone_id, version, template)):
        raise ProviderRejectedError("configuration_missing")
    payload = {
        "messaging_product": "whatsapp",
        "to": number.lstrip("+"),
        "type": "template",
        "template": {
            "name": template,
            "language": {"code": os.getenv("WHATSAPP_TEMPLATE_LANGUAGE", "en")},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": str(value)} for value in params],
                }
            ],
        },
    }
    request = Request(
        f"https://graph.facebook.com/{version}/{phone_id}/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            result = json.load(response)
    except HTTPError as exc:
        if exc.code == 429:
            raise ProviderRateLimitedError("rate_limited") from exc
        if 400 <= exc.code < 500:
            raise ProviderRejectedError(f"http_{exc.code}") from exc
        # 5xx may follow a successfully received request.
        raise DeliveryUncertainError("upstream_ambiguous") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise DeliveryUncertainError("transport_ambiguous") from exc
    try:
        return result["messages"][0]["id"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise DeliveryUncertainError("response_ambiguous") from exc


def _discover_due(now):
    """Generate one event per consenting recipient and booking/slot/kind."""
    confirmed = {
        "status": LiveClassBooking.Status.CONFIRMED,
        "paid_at__isnull": False,
        "slot__starts_at__gt": now,
    }
    # New paid bookings receive confirmation promptly; existing bookings
    # receive reminders starting 30 minutes before class. Separate scans
    # prevent newer bookings from starving older soon-to-start sessions.
    newest = LiveClassBooking.objects.filter(**confirmed).order_by("-paid_at")[:500]
    upcoming = LiveClassBooking.objects.filter(
        **confirmed, slot__starts_at__lte=now + timedelta(minutes=30)
    ).order_by("slot__starts_at")[:500]
    seen = set()
    for booking in list(newest) + list(upcoming):
        if booking.pk in seen:
            continue
        seen.add(booking.pk)
        prefs = WhatsAppPreference.objects.filter(
            opted_in=True, consent_recorded_at__isnull=False
        ).filter(Q(student_id=booking.student_id) | Q(tutor_id=booking.slot.tutor_id))
        kinds = [WhatsAppDelivery.Kind.CONFIRMATION]
        if booking.slot.starts_at <= now + timedelta(minutes=30):
            kinds.append(WhatsAppDelivery.Kind.REMINDER)
        for preference in prefs:
            for kind in kinds:
                WhatsAppDelivery.objects.get_or_create(
                    booking=booking,
                    preference=preference,
                    kind=kind,
                    slot_start=booking.slot.starts_at,
                    defaults={"next_attempt_at": now},
                )


def _deliver(delivery_id, now):
    # Lock and claim the event before the external side effect. A second
    # worker/Beat process cannot claim it again while the first is running.
    with transaction.atomic():
        delivery = (
            WhatsAppDelivery.objects.select_for_update()
            .select_related("booking__slot__tutor", "preference")
            .get(pk=delivery_id)
        )
        if delivery.status not in {
            WhatsAppDelivery.Status.PENDING,
            WhatsAppDelivery.Status.RETRY,
        }:
            return False
        if delivery.next_attempt_at and delivery.next_attempt_at > now:
            return False
        booking = delivery.booking
        pref = delivery.preference
        if (
            not pref.opted_in
            or not pref.consent_recorded_at
            or not re.fullmatch(r"\+[1-9][0-9]{7,14}", pref.number)
            or booking.status != LiveClassBooking.Status.CONFIRMED
            or booking.paid_at is None
            or booking.slot.starts_at <= now
            or booking.slot.starts_at != delivery.slot_start
            or (
                delivery.kind == WhatsAppDelivery.Kind.REMINDER
                and booking.slot.starts_at > now + timedelta(minutes=30)
            )
        ):
            delivery.status = WhatsAppDelivery.Status.SKIPPED
            delivery.error_code = "ineligible_or_opted_out"
            delivery.save(update_fields=["status", "error_code"])
            return False
        delivery.status = WhatsAppDelivery.Status.SENDING
        delivery.attempts += 1
        delivery.last_attempt_at = now
        delivery.next_attempt_at = None
        delivery.save(
            update_fields=["status", "attempts", "last_attempt_at", "next_attempt_at"]
        )
        number = pref.number
        template = os.getenv(
            "WHATSAPP_REMINDER_TEMPLATE"
            if delivery.kind == WhatsAppDelivery.Kind.REMINDER
            else "WHATSAPP_CONFIRMATION_TEMPLATE",
            "",
        )
        when = timezone.localtime(booking.slot.starts_at, SAST).strftime(
            "%d %b %Y %H:%M SAST"
        )
        parameters = [
            booking.reference,
            booking.topic,
            when,
            booking.slot.tutor_display_name,
        ]
        attempt = delivery.attempts

    try:
        provider_id = _send_template(number, template, parameters)
    except ProviderRateLimitedError:
        if attempt < MAX_ATTEMPTS:
            WhatsAppDelivery.objects.filter(
                pk=delivery_id, status=WhatsAppDelivery.Status.SENDING
            ).update(
                status=WhatsAppDelivery.Status.RETRY,
                error_code="rate_limited",
                next_attempt_at=timezone.now()
                + timedelta(seconds=60 * (2 ** (attempt - 1))),
            )
        else:
            WhatsAppDelivery.objects.filter(
                pk=delivery_id, status=WhatsAppDelivery.Status.SENDING
            ).update(status=WhatsAppDelivery.Status.FAILED, error_code="rate_limited")
    except ProviderRejectedError:
        WhatsAppDelivery.objects.filter(
            pk=delivery_id, status=WhatsAppDelivery.Status.SENDING
        ).update(status=WhatsAppDelivery.Status.FAILED, error_code="provider_rejected")
    except Exception:
        # Requests that time out, crash, or return an ambiguous response
        # might already have reached Meta. Escalate for manual review.
        logger.warning("WhatsApp outcome uncertain for delivery_id=%s", delivery_id)
        WhatsAppDelivery.objects.filter(
            pk=delivery_id, status=WhatsAppDelivery.Status.SENDING
        ).update(status=WhatsAppDelivery.Status.UNKNOWN, error_code="uncertain_outcome")
    else:
        WhatsAppDelivery.objects.filter(
            pk=delivery_id, status=WhatsAppDelivery.Status.SENDING
        ).update(
            status=WhatsAppDelivery.Status.SENT,
            provider_id=provider_id,
            sent_at=timezone.now(),
            error_code="",
        )
        return True
    return False


@shared_task(ignore_result=True)
def dispatch_whatsapp_booking_notifications():
    """Beat invokes this every minute; never affects the email workflow."""
    if not getattr(settings, "WHATSAPP_NOTIFICATIONS_ENABLED", False):
        return 0
    now = timezone.now()
    # A worker may crash after Meta accepts a message but before persisting
    # its ID. An abandoned claim is indeterminate, NOT safe to retry.
    WhatsAppDelivery.objects.filter(
        status=WhatsAppDelivery.Status.SENDING,
        last_attempt_at__lt=now - timedelta(minutes=5),
    ).update(status=WhatsAppDelivery.Status.UNKNOWN, error_code="abandoned_claim")
    _discover_due(now)
    due = list(
        WhatsAppDelivery.objects.filter(
            status__in=[WhatsAppDelivery.Status.PENDING, WhatsAppDelivery.Status.RETRY]
        )
        .filter(Q(next_attempt_at__lte=now) | Q(next_attempt_at__isnull=True))
        .order_by("created_at", "pk")
        .values_list("pk", flat=True)[:300]
    )
    return sum(_deliver(pk, now) for pk in due)
