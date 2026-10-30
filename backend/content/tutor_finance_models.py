"""Financial records for tutor work. Never expose these models through public serializers."""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from .models import TimeStampedModel


class TutorPaymentProfile(TimeStampedModel):
    tutor = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payment_profile")
    account_holder = models.CharField(max_length=160, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    branch_code = models.CharField(max_length=20, blank=True)
    encrypted_account_number = models.TextField(blank=True, editable=False)
    account_last_four = models.CharField(max_length=4, blank=True, editable=False)
    provider_recipient_id = models.CharField(
        max_length=120, blank=True, help_text="Verified recipient token, not an API secret."
    )
    recipient_verified_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=False, help_text="Enable after bank ownership and contract checks.")

    def clean(self):
        super().clean()
        if self.is_active and (
            not self.encrypted_account_number
            or not self.account_holder
            or not self.bank_name
            or not self.provider_recipient_id
            or not self.recipient_verified_at
        ):
            raise ValidationError("A verified payout recipient and encrypted bank account are required for activation.")

    def __str__(self):
        return f"{self.tutor.get_username()} / {self.bank_name or 'unconfigured'} / ****{self.account_last_four}"


class TutorContract(TimeStampedModel):
    class Service(models.TextChoices):
        COURSE = "course", "Course sale"
        LIVE_CLASS = "live_class", "Online class"
        VIDEO = "video", "Topical video"

    tutor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="finance_contracts")
    service = models.CharField(max_length=20, choices=Service.choices)
    tutor_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("100.00"))],
        help_text="Tutor percentage of gross sale: 60 means tutor 60%, Amaris 40%.",
    )
    effective_from = models.DateTimeField(default=timezone.now)
    effective_until = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    contract_reference = models.CharField(max_length=100, help_text="Signed agreement identifier")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("tutor", "service", "effective_from"), name="tutor_contract_start_unique"),
        ]

    def clean(self):
        super().clean()
        if self.effective_until and self.effective_until <= self.effective_from:
            raise ValidationError("Contract expiry must follow its effective date.")
        if self.tutor_id and self.is_active:
            overlaps = TutorContract.objects.filter(tutor_id=self.tutor_id, service=self.service, is_active=True)
            if self.pk:
                overlaps = overlaps.exclude(pk=self.pk)
            for other in overlaps:
                if (self.effective_until is None or other.effective_from < self.effective_until) and (
                    other.effective_until is None or self.effective_from < other.effective_until
                ):
                    raise ValidationError("Tutor contracts for the same service must not overlap.")

    def __str__(self):
        return f"{self.tutor} / {self.get_service_display()} / tutor {self.tutor_percent}%"


class TutorCourseAssignment(TimeStampedModel):
    course = models.ForeignKey("content.Course", on_delete=models.PROTECT, related_name="tutor_assignments")
    tutor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="course_assignments")
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("course", "tutor"), name="tutor_course_unique")]


class TutorEarning(TimeStampedModel):
    class State(models.TextChoices):
        HELD = "held", "Held until delivery / settlement"
        READY = "ready", "Eligible for payout"
        PAID = "paid", "Paid out"
        REVERSED = "reversed", "Refunded / reversed"

    tutor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="tutor_earnings")
    contract = models.ForeignKey(TutorContract, on_delete=models.PROTECT, related_name="earnings")
    service = models.CharField(max_length=20, choices=TutorContract.Service.choices)
    source_reference = models.CharField(max_length=100)
    service_label = models.CharField(max_length=180)
    gross = models.DecimalField(max_digits=12, decimal_places=2)
    tutor_percent = models.DecimalField(max_digits=5, decimal_places=2)
    tutor_amount = models.DecimalField(max_digits=12, decimal_places=2)
    academy_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="ZAR")
    state = models.CharField(max_length=12, choices=State.choices, default=State.HELD, db_index=True)
    payment_verified_at = models.DateTimeField()
    service_delivered_at = models.DateTimeField(blank=True, null=True)
    eligible_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("service", "source_reference"), name="tutor_earning_source_unique")
        ]
        indexes = [models.Index(fields=("tutor", "service", "state"), name="tutor_earnings_summary_idx")]

    def __str__(self):
        return f"{self.tutor_id} {self.service} {self.source_reference}"


class TutorPayout(TimeStampedModel):
    class State(models.TextChoices):
        AWAITING_PROVIDER = "awaiting_provider", "Awaiting payout integration"
        PROCESSING = "processing", "Processing"
        PAID = "paid", "Confirmed paid"
        FAILED = "failed", "Failed"

    earning = models.OneToOneField(TutorEarning, on_delete=models.PROTECT, related_name="payout")
    state = models.CharField(max_length=20, choices=State.choices, default=State.AWAITING_PROVIDER)
    provider_name = models.CharField(max_length=60, blank=True)
    provider_reference = models.CharField(max_length=160, blank=True)
    bank_last_four = models.CharField(max_length=4, blank=True)
    confirmed_at = models.DateTimeField(blank=True, null=True)
    receipt_emailed_at = models.DateTimeField(blank=True, null=True)
    failure_code = models.CharField(max_length=64, blank=True)

    def __str__(self):
        return f"{self.earning.source_reference}: {self.state}"



class TutorActivityStatement(TimeStampedModel):
    """Immutable 30-day earnings snapshot; report generation never pays a tutor."""

    class State(models.TextChoices):
        DRAFT = "draft", "Draft / awaiting archive"
        ARCHIVED = "archived", "Archived / awaiting delivery"
        DELIVERED = "delivered", "Tutor and administrator notified"

    tutor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="activity_statements"
    )
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    report_number = models.CharField(max_length=96, unique=True)
    state = models.CharField(max_length=16, choices=State.choices, default=State.DRAFT, db_index=True)
    snapshot = models.JSONField(default=dict, editable=False)
    pdf_storage_path = models.CharField(max_length=512, blank=True, editable=False)
    pdf_sha256 = models.CharField(max_length=64, blank=True, editable=False)
    tutor_emailed_at = models.DateTimeField(blank=True, null=True, editable=False)
    admin_emailed_at = models.DateTimeField(blank=True, null=True, editable=False)

    class Meta:
        ordering = ("-period_end", "tutor_id")
        constraints = [
            models.UniqueConstraint(
                fields=("tutor", "period_start", "period_end"),
                name="tutor_stmt_unique_period",
            ),
            models.CheckConstraint(
                condition=models.Q(period_end__gt=models.F("period_start")),
                name="tutor_stmt_valid_period",
            ),
        ]
        indexes = [models.Index(fields=("state", "period_end"), name="tutor_stmt_pending_idx")]

    def __str__(self):
        return self.report_number
