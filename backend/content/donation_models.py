from __future__ import annotations

import uuid
from django.db import models
from .models import TimeStampedModel


class DonationContribution(TimeStampedModel):
    """Server-owned PayFast contribution; never confers a student enrollment."""

    class Purpose(models.TextChoices):
        LEARNER = "learner", "Support a learner"
        RESOURCES = "resources", "Learning resources"
        TECHNOLOGY = "technology", "Technology and accessibility"
        GENERAL = "general", "General education project"

    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting verification"
        PAID = "paid", "Verified by PayFast"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=80, unique=True, editable=False)
    donor_name = models.CharField(max_length=100)
    donor_email = models.EmailField()
    purpose = models.CharField(max_length=16, choices=Purpose.choices)
    amount = models.DecimalField(max_digits=9, decimal_places=2)
    currency = models.CharField(max_length=3, default="ZAR")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    provider_reference = models.CharField(max_length=160, null=True, blank=True, unique=True, editable=False)
    gateway_verified_at = models.DateTimeField(null=True, blank=True, editable=False)
    paid_at = models.DateTimeField(null=True, blank=True, editable=False)
    receipt_sent_at = models.DateTimeField(null=True, blank=True, editable=False)
    receipt_error = models.CharField(max_length=60, blank=True, editable=False)
    last_callback_status = models.CharField(max_length=16, blank=True, editable=False)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("status", "-created_at"), name="donation_status_created_idx")]

    def __str__(self):
        return f"{self.reference} — {self.get_status_display()}"
