"""Fixed-term curriculum access; checkout never grants an entitlement."""

import uuid

from django.db import models

from .models import StudentRecord, TimeStampedModel


class CurriculumSubscription(TimeStampedModel):
    class Curriculum(models.TextChoices):
        CAPS = "caps", "CAPS"
        IEB = "ieb", "IEB"
        NATED = "nated", "TVET NATED"
        NCV = "ncv", "TVET NC(V)"
        UNIVERSITY = "university", "University / UNISA"

    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting payment"
        PAID = "paid", "Payment confirmed"
        REFUNDED = "refunded", "Refunded / reversed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(StudentRecord, on_delete=models.PROTECT, related_name="curriculum_subscriptions")
    reference = models.CharField(max_length=64, unique=True, editable=False)
    idempotency_key = models.CharField(max_length=64, editable=False)
    curriculum = models.CharField(max_length=16, choices=Curriculum.choices)
    months = models.PositiveSmallIntegerField(choices=[(4, "Four months"), (8, "Eight months")])
    amount = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    currency = models.CharField(max_length=3, default="ZAR", editable=False)
    gateway_mode = models.CharField(max_length=8, editable=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    provider_reference = models.CharField(max_length=160, unique=True, null=True, blank=True, editable=False)
    gateway_verified_at = models.DateTimeField(null=True, blank=True, editable=False)
    starts_at = models.DateTimeField(null=True, blank=True, editable=False)
    ends_at = models.DateTimeField(null=True, blank=True, editable=False)
    pdf_storage_path = models.CharField(max_length=512, blank=True, editable=False)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["student", "idempotency_key"], name="subscription_checkout_key_unique"),
            models.CheckConstraint(condition=models.Q(months__in=[4, 8]), name="subscription_valid_term"),
            models.CheckConstraint(
                condition=(models.Q(months=4, amount="3800.00") | models.Q(months=8, amount="7600.00")),
                name="subscription_fixed_price",
            ),
        ]
        indexes = [models.Index(fields=["student", "status", "ends_at"], name="sub_student_access_idx")]

    def __str__(self):
        return f"{self.reference} — {self.get_curriculum_display()} / {self.months} months"
