"""Private, durable audit and Admin notification for successful tutor video submissions."""

import uuid

from django.conf import settings
from django.db import models

from .models import TimeStampedModel


class TutorVideoUpload(TimeStampedModel):
    class Delivery(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENDING = "sending", "Sending - do not resend"
        SENT = "sent", "Accepted by mail provider"
        REVIEW = "review", "Delivery needs review"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tutor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="video_upload_events")
    video = models.ForeignKey("content.VideoAsset", on_delete=models.PROTECT, related_name="upload_events")
    idempotency_key = models.CharField(max_length=64, editable=False)
    fingerprint = models.CharField(max_length=64, editable=False)
    payload = models.JSONField(default=dict, editable=False)
    recipient = models.EmailField(editable=False)
    delivery_status = models.CharField(max_length=12, choices=Delivery.choices, default=Delivery.QUEUED)
    attempts = models.PositiveSmallIntegerField(default=0, editable=False)
    next_attempt_at = models.DateTimeField(null=True, blank=True, editable=False)
    sending_at = models.DateTimeField(null=True, blank=True, editable=False)
    sent_at = models.DateTimeField(null=True, blank=True, editable=False)
    error_code = models.CharField(max_length=40, blank=True, editable=False)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["tutor", "idempotency_key"], name="tutor_video_upload_key_unique")
        ]
        indexes = [models.Index(fields=["delivery_status", "next_attempt_at"], name="tutor_video_alert_due_idx")]

    def __str__(self):
        return f"Tutor video upload {self.id}"
