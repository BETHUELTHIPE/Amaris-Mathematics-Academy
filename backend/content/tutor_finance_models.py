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
        if self.is_active and (not self.encrypted_account_number or not self.account_holder or not self.bank_name):
            raise ValidationError("Bank ownership and an encrypted account are required before activation.")

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


class TutorVideoRequest(TimeStampedModel):
    """Dedicated verified payment object. Never accept a frontend 'paid' flag."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending payment"
        PAID = "paid", "Paid / awaiting video"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    reference = models.CharField(max_length=100, unique=True)
    idempotency_key = models.CharField(max_length=64, unique=True)
    student = models.ForeignKey(
        "content.StudentRecord", on_delete=models.PROTECT, related_name="topical_video_requests"
    )
    tutor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="video_requests")
    topic = models.CharField(max_length=180)
    programme = models.CharField(max_length=60)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("1.00"))])
    currency = models.CharField(max_length=3, default="ZAR")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    provider_reference = models.CharField(max_length=160, blank=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    gateway_verified_at = models.DateTimeField(blank=True, null=True)
    delivered_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.reference


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
