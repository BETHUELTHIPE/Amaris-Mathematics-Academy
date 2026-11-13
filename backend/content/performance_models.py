"""Private, immutable academy performance snapshots and conservative email outbox."""

import uuid

from django.db import models
from django.utils import timezone

from amaris_cms.storage import admin_private_storage
from content.models import TimeStampedModel


class PerformanceSchedule(TimeStampedModel):
    payment_mode = models.CharField(max_length=8, primary_key=True, choices=[("live", "Live"), ("sandbox", "Sandbox")])
    anchor_date = models.DateField(default=timezone.localdate, editable=False)

    class Meta:
        verbose_name = "Performance report schedule"

    def __str__(self):
        return f"{self.payment_mode} reports every 14 days from {self.anchor_date}"


class PerformanceDigest(TimeStampedModel):
    class Delivery(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENDING = "sending", "Sending - do not resend"
        SENT = "sent", "Accepted by mail provider"
        REVIEW = "review", "Delivery needs review"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment_mode = models.CharField(max_length=8, choices=[("live", "Live"), ("sandbox", "Sandbox")], editable=False)
    period_start = models.DateField(editable=False)
    period_end = models.DateField(editable=False, help_text="Exclusive end date at 00:00 SAST.")
    snapshot = models.JSONField(default=dict, editable=False)
    pdf = models.FileField(max_length=250, editable=False, storage=admin_private_storage)
    pdf_sha256 = models.CharField(max_length=64, editable=False)
    recipient = models.EmailField(editable=False)
    delivery_status = models.CharField(max_length=12, choices=Delivery.choices, default=Delivery.QUEUED)
    attempts = models.PositiveSmallIntegerField(default=0, editable=False)
    next_attempt_at = models.DateTimeField(null=True, blank=True, editable=False)
    sending_at = models.DateTimeField(null=True, blank=True, editable=False)
    sent_at = models.DateTimeField(null=True, blank=True, editable=False)
    error_code = models.CharField(max_length=40, blank=True, editable=False)

    class Meta:
        ordering = ["-period_start"]
        verbose_name = "Performance report"
        constraints = [
            models.UniqueConstraint(fields=["payment_mode", "period_start"], name="performance_period_unique")
        ]
        indexes = [models.Index(fields=["delivery_status", "next_attempt_at"], name="performance_digest_due_idx")]

    def __str__(self):
        return f"{self.payment_mode} performance / {self.period_start} to {self.period_end} (exclusive)"
