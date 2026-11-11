"""Private, administrator-approved sponsor records."""

import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from .models import Enrollment, StudentRecord, TimeStampedModel, TutorAvailabilitySlot


class SponsorAccount(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supabase_user_id = models.UUIDField(
        unique=True, help_text="Verified Supabase Auth user ID. Set by an administrator."
    )
    name = models.CharField(max_length=120)
    organisation = models.CharField(max_length=180, blank=True)
    is_active = models.BooleanField(
        default=False, help_text="Approve access only after verifying this sponsor's identity."
    )
    annual_target = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])

    class Meta:
        ordering = ("name",)

    @property
    def is_authenticated(self):
        return True

    def __str__(self):
        return self.organisation or self.name


class SponsorContribution(TimeStampedModel):
    class Status(models.TextChoices):
        PLEDGED = "pledged", "Pledged"
        RECEIVED = "received", "Received"
        REFUNDED = "refunded", "Refunded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sponsor = models.ForeignKey(SponsorAccount, on_delete=models.PROTECT, related_name="contributions")
    reference = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLEDGED)
    received_at = models.DateTimeField(blank=True, null=True)
    description = models.CharField(max_length=180, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=("sponsor", "status", "received_at"), name="sponsor_contribution_idx")]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="sponsor_contribution_positive"),
            models.CheckConstraint(
                condition=~models.Q(status="received") | models.Q(received_at__isnull=False),
                name="sponsor_received_timestamp",
            ),
        ]

    def clean(self):
        super().clean()
        if self.status == self.Status.RECEIVED and not self.received_at:
            raise ValidationError({"received_at": "Record the verified receipt date before marking funding received."})

    def __str__(self):
        return self.reference


class SponsorAllocation(TimeStampedModel):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sponsor = models.ForeignKey(SponsorAccount, on_delete=models.PROTECT, related_name="allocations")
    student = models.ForeignKey(StudentRecord, on_delete=models.PROTECT, related_name="sponsor_allocations")
    learner_label = models.CharField(
        max_length=80, help_text="Sponsor-visible alias. Use a pseudonym unless sharing is authorised."
    )
    programme = models.CharField(max_length=20, choices=TutorAvailabilitySlot.Programme.choices)
    level = models.CharField(max_length=80)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLANNED)
    starts_on = models.DateField()
    ends_on = models.DateField(blank=True, null=True)
    enrollment = models.ForeignKey(Enrollment, on_delete=models.PROTECT, blank=True, null=True)
    share_progress = models.BooleanField(default=False)
    progress_consented_at = models.DateTimeField(
        blank=True, null=True, help_text="Record permission to share this enrollment's progress."
    )

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=("sponsor", "status"), name="sponsor_allocation_idx")]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="sponsor_allocation_positive"),
            models.CheckConstraint(
                condition=models.Q(ends_on__isnull=True) | models.Q(ends_on__gte=models.F("starts_on")),
                name="sponsor_allocation_dates",
            ),
            models.CheckConstraint(
                condition=models.Q(share_progress=False)
                | (models.Q(enrollment__isnull=False) & models.Q(progress_consented_at__isnull=False)),
                name="sponsor_progress_consent",
            ),
        ]

    def clean(self):
        super().clean()
        if self.enrollment is not None and self.enrollment.student_id != self.student_id:
            raise ValidationError({"enrollment": "Choose an enrollment belonging to this sponsored student."})
        if self.share_progress and (not self.enrollment_id or not self.progress_consented_at):
            raise ValidationError({"share_progress": "A linked enrollment and recorded sharing consent are required."})
        if self.ends_on and self.ends_on < self.starts_on:
            raise ValidationError({"ends_on": "The end date must be on or after the start date."})

    def __str__(self):
        return f"{self.learner_label} · {self.sponsor}"
