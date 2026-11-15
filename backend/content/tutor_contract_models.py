"""Immutable tutor employment agreements and their private delivery audit."""

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from amaris_cms.storage import tutor_private_storage
from content.models import TimeStampedModel


class TutorEmploymentContract(TimeStampedModel):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Awaiting employer countersignature"
        ACCEPTED = "accepted", "Accepted and countersigned"
        DECLINED = "declined", "Declined by employer"

    class Delivery(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENDING = "sending", "Sending - do not resend"
        SENT = "sent", "Accepted by mail provider"
        REVIEW = "review", "Delivery needs review"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tutor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="employment_contracts")
    idempotency_key = models.CharField(max_length=64, editable=False)
    fingerprint = models.CharField(max_length=64, editable=False)
    terms_version = models.CharField(max_length=40, editable=False)
    payload = models.JSONField(default=dict, editable=False)
    service_terms = models.JSONField(default=list, editable=False)
    statutory_hourly_floor = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SUBMITTED)
    review_notes = models.TextField(blank=True, max_length=3000, help_text="Visible to the tutor in their dashboard.")
    employer_signature_name = models.CharField(max_length=150, blank=True)
    effective_date = models.DateField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reviewed_employment_contracts",
        editable=False,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, editable=False)
    employee_pdf = models.FileField(max_length=250, editable=False, storage=tutor_private_storage)
    employee_pdf_sha256 = models.CharField(max_length=64, editable=False)
    executed_pdf = models.FileField(max_length=250, blank=True, editable=False, storage=tutor_private_storage)
    executed_pdf_sha256 = models.CharField(max_length=64, blank=True, editable=False)
    recipient = models.EmailField(editable=False)
    delivery_status = models.CharField(max_length=12, choices=Delivery.choices, default=Delivery.QUEUED)
    attempts = models.PositiveSmallIntegerField(default=0, editable=False)
    next_attempt_at = models.DateTimeField(null=True, blank=True, editable=False)
    sending_at = models.DateTimeField(null=True, blank=True, editable=False)
    sent_at = models.DateTimeField(null=True, blank=True, editable=False)
    error_code = models.CharField(max_length=40, blank=True, editable=False)

    class Meta:
        verbose_name = "Tutor employment contract"
        verbose_name_plural = "Tutor employment contracts"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["tutor", "idempotency_key"], name="tutor_employment_key_unique")
        ]
        indexes = [models.Index(fields=["delivery_status", "next_attempt_at"], name="tutor_employment_due_idx")]

    def clean(self):
        if self.statutory_hourly_floor < Decimal("30.23"):
            raise ValidationError({"statutory_hourly_floor": "The 2026 statutory floor cannot be reduced."})
        if self.status == self.Status.ACCEPTED and (
            not self.employer_signature_name.strip() or not self.effective_date
        ):
            raise ValidationError("Employer signature and effective date are required before acceptance.")
        if self.status != self.Status.ACCEPTED and (self.employer_signature_name or self.effective_date):
            raise ValidationError("Employer signature details may be recorded only when accepting the contract.")

    def __str__(self):
        return f"Tutor employment contract - {self.tutor} - {self.id}"
