"""Private, immutable tutor leave and resignation submissions with delivery audit."""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from amaris_cms.storage import tutor_private_storage
from content.models import TimeStampedModel


class TutorPersonnelForm(TimeStampedModel):
    class Kind(models.TextChoices):
        LEAVE = "leave", "Leave application"
        RESIGNATION = "resignation", "Withdrawal / resignation notice"

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted for review"
        APPROVED = "approved", "Leave approved"
        DECLINED = "declined", "Leave declined"
        ACKNOWLEDGED = "acknowledged", "Resignation acknowledged"

    class LeaveType(models.TextChoices):
        ANNUAL = "annual", "Annual leave"
        SICK = "sick", "Sick leave"
        PERSONAL = "personal", "Personal / family responsibility"
        STUDY = "study", "Study leave"
        OTHER = "other", "Other"

    class Delivery(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENDING = "sending", "Sending - do not resend"
        SENT = "sent", "Accepted by mail provider"
        REVIEW = "review", "Delivery needs review"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tutor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="personnel_forms")
    kind = models.CharField(max_length=16, choices=Kind.choices, editable=False)
    idempotency_key = models.CharField(max_length=64, editable=False)
    fingerprint = models.CharField(max_length=64, editable=False)
    payload = models.JSONField(default=dict, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SUBMITTED)
    review_notes = models.TextField(blank=True, max_length=3000, help_text="Visible to the tutor in their dashboard.")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reviewed_personnel_forms",
        editable=False,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, editable=False)
    pdf = models.FileField(max_length=250, editable=False, storage=tutor_private_storage)
    pdf_sha256 = models.CharField(max_length=64, editable=False)
    recipient = models.EmailField(editable=False)
    delivery_status = models.CharField(max_length=12, choices=Delivery.choices, default=Delivery.QUEUED)
    attempts = models.PositiveSmallIntegerField(default=0, editable=False)
    next_attempt_at = models.DateTimeField(null=True, blank=True, editable=False)
    sending_at = models.DateTimeField(null=True, blank=True, editable=False)
    sent_at = models.DateTimeField(null=True, blank=True, editable=False)
    error_code = models.CharField(max_length=40, blank=True, editable=False)

    class Meta:
        verbose_name = "Tutor leave / resignation form"
        verbose_name_plural = "Tutor leave / resignation forms"
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["tutor", "idempotency_key"], name="tutor_personnel_key_unique")]
        indexes = [models.Index(fields=["delivery_status", "next_attempt_at"], name="tutor_personnel_due_idx")]

    def clean(self):
        allowed = {self.Status.SUBMITTED}
        allowed.update(
            {self.Status.APPROVED, self.Status.DECLINED} if self.kind == self.Kind.LEAVE else {self.Status.ACKNOWLEDGED}
        )
        if self.status not in allowed:
            raise ValidationError({"status": "Choose a review status appropriate to this form type."})

    def __str__(self):
        return f"{self.get_kind_display()} - {self.id}"
