"""Opt-in only WhatsApp booking notifications through Meta Cloud API."""
import json
import logging
import os
import re
from datetime import timedelta
from urllib.request import Request, urlopen

from celery import shared_task
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from .models import LiveClassBooking

logger = logging.getLogger(__name__)


class WhatsAppPreference(models.Model):
    student = models.OneToOneField(
        "content.StudentRecord", on_delete=models.CASCADE, null=True,
        blank=True, related_name="whatsapp_preference"
    )
    tutor = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True,
        blank=True, related_name="whatsapp_preference"
    )
    number = models.CharField(max_length=20, help_text="E.164 number, e.g. +27821234567")
    opted_in = models.BooleanField(default=False)
    consent_recorded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(student__isnull=False, tutor__isnull=True)
                    | models.Q(student__isnull=True, tutor__isnull=False)
                ), name="whatsapp_exactly_one_recipient"
            )
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if bool(self.student_id) == bool(self.tutor_id):
            raise ValidationError("Choose exactly one student or tutor.")
        if not re.fullmatch(r"\+[1-9][0-9]{7,14}", self.number):
            raise ValidationError("Use E.164 format such as +27821234567.")

    def __str__(self):
        return self.number


class WhatsAppDelivery(models.Model):
    class Kind(models.TextChoices):
        CONFIRMATION = "confirmation", "Booking confirmation"
        REMINDER = "reminder", "30-minute reminder"
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Accepted by provider"
        SKIPPED = "skipped", "Skipped"
        FAILED = "failed", "Failed"

    booking = models.ForeignKey(
        LiveClassBooking, related_name="whatsapp_deliveries", on_delete=models.CASCADE
    )
    preference = models.ForeignKey(WhatsAppPreference, on_delete=models.PROTECT)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    slot_start = models.DateTimeField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    sent_at = models.DateTimeField(null=True, blank=True)
    provider_id = models.CharField(max_length=128, blank=True)\n    receipt_status = models.CharField(max_length=16, blank=True, default="")
    error_code = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["booking", "preference", "kind", "slot_start"],
                name="whatsapp_unique_booking_event"
            )
        ]


def _send_template(number, template, params):
    token = os.getenv("WHATSAPP_CLOUD_TOKEN", "")
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    version = os.getenv("WHATSAPP_GRAPH_API_VERSION", "")
    if not token or not phone_id or not version or not template:
        raise RuntimeError("WhatsApp Cloud API is not configured")
    payload = {
        "messaging_product": "whatsapp",
        "to": number.lstrip("+"),
        "type": "template",
        "template": {
            "name": template,
            "language": {"code": os.getenv("WHATSAPP_TEMPLATE_LANGUAGE", "en")},
            "components": [{
                "type": "body",
                "parameters": [{"type": "text", "text": str(value)} for value in params],
            }],
        },
    }
    req = Request(
        f"https://graph.facebook.com/{version}/{phone_id}/messages",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=10) as response:
        result = json.load(response)
    return result["messages"][0]["id"]


@shared_task(ignore_result=True)
def dispatch_whatsapp_booking_notifications():
    """Invoked by Beat every minute; email delivery remains independent."""
    if not getattr(settings, "WHATSAPP_NOTIFICATIONS_ENABLED", False):
        return 0
    now = timezone.now()
    bookings = LiveClassBooking.objects.filter(
        status=LiveClassBooking.Status.CONFIRMED,
        paid_at__isnull=False,
        slot__starts_at__gt=now,
    ).select_related("student", "slot", "slot__tutor").order_by("slot__starts_at")[:100]
    sent = 0
    for booking in bookings:
        prefs = WhatsAppPreference.objects.filter(
            opted_in=True, consent_recorded_at__isnull=False
        ).filter(
            models.Q(student=booking.student) | models.Q(tutor=booking.slot.tutor)
        )
        kind = (
            WhatsAppDelivery.Kind.REMINDER
            if booking.slot.starts_at <= now + timedelta(minutes=30)
            else WhatsAppDelivery.Kind.CONFIRMATION
        )
        # Prioritise confirmation for every recipient, then reminder near start.
        for preference in prefs:
            kinds = [WhatsAppDelivery.Kind.CONFIRMATION]
            if kind == WhatsAppDelivery.Kind.REMINDER:
                kinds.append(WhatsAppDelivery.Kind.REMINDER)
            for selected in kinds:
                with transaction.atomic():
                    delivery, created = WhatsAppDelivery.objects.get_or_create(
                        booking=booking, preference=preference,
                        kind=selected, slot_start=booking.slot.starts_at,
                    )
                    if not created:
                        continue
                if not re.fullmatch(r"\+[1-9][0-9]{7,14}", preference.number):
                    delivery.status = WhatsAppDelivery.Status.SKIPPED
                    delivery.error_code = "invalid_number"
                else:
                    try:
                        template = os.getenv(
                            "WHATSAPP_REMINDER_TEMPLATE" if selected == WhatsAppDelivery.Kind.REMINDER
                            else "WHATSAPP_CONFIRMATION_TEMPLATE", ""
                        )
                        from django.utils import timezone as tz
                        when = tz.localtime(booking.slot.starts_at).strftime("%d %b %Y %H:%M SAST")
                        delivery.provider_id = _send_template(
                            preference.number, template,
                            [booking.reference, booking.topic, when, booking.slot.tutor_display_name],
                        )
                        delivery.status = WhatsAppDelivery.Status.SENT
                        delivery.sent_at = timezone.now()
                        sent += 1
                    except Exception as exc:
                        logger.warning("WhatsApp delivery failed: %s", type(exc).__name__)
                        delivery.status = WhatsAppDelivery.Status.FAILED
                        delivery.error_code = type(exc).__name__[:80]
                delivery.save(update_fields=["status", "error_code", "provider_id", "sent_at"])
    return sent
