"""Private subscription attendance, learning history and durable report delivery."""

import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from .models import TimeStampedModel


class SubscriptionSession(TimeStampedModel):
    class Status(models.TextChoices):
        PLANNED = "planned", "Attendance not recorded"
        ATTENDED = "attended", "Attended in full"
        PARTIAL = "partial", "Partially attended"
        ABSENT = "absent", "Missed"
        CANCELLED = "cancelled", "Cancelled"

    subscription = models.ForeignKey(
        "content.CurriculumSubscription", on_delete=models.PROTECT, related_name="sessions"
    )
    tutor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="subscription_sessions")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    subject = models.CharField(max_length=100)
    level = models.CharField(max_length=80, blank=True)
    topic = models.CharField(max_length=180)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLANNED)
    joined_at = models.DateTimeField(null=True, blank=True)
    left_at = models.DateTimeField(null=True, blank=True)
    learning_summary = models.TextField(blank=True, max_length=1000, help_text="Student-facing learning outcomes only.")
    tutor_feedback = models.TextField(blank=True, max_length=1000, help_text="Shared with the student in their report.")
    next_steps = models.TextField(
        blank=True, max_length=1000, help_text="Practice or homework shared with the student."
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        editable=False,
        on_delete=models.PROTECT,
        related_name="verified_subscription_sessions",
    )
    verified_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["starts_at", "pk"]
        indexes = [models.Index(fields=["subscription", "starts_at"], name="sub_session_period_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at=F("starts_at") + timedelta(hours=2)), name="sub_session_two_hours"
            ),
            models.CheckConstraint(
                condition=(
                    Q(joined_at__isnull=True, left_at__isnull=True)
                    | Q(
                        joined_at__isnull=False,
                        left_at__isnull=False,
                        joined_at__gte=F("starts_at"),
                        left_at__lte=F("ends_at"),
                        left_at__gt=F("joined_at"),
                    )
                ),
                name="sub_session_attendance_bounds",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(status__in=["attended", "partial", "absent"])
                    | Q(verified_at__isnull=False, verified_by__isnull=False)
                ),
                name="sub_session_confirmation_required",
            ),
        ]

    def clean(self):
        super().clean()
        if not self.subscription_id or not self.starts_at or not self.ends_at:
            return
        sub = self.subscription
        if sub.status != "paid" or not sub.gateway_verified_at or not sub.starts_at or not sub.ends_at:
            raise ValidationError("Record sessions only against a verified paid subscription.")
        if not sub.starts_at <= self.starts_at < self.ends_at <= sub.ends_at:
            raise ValidationError("The session must be inside the subscription period.")
        if self.ends_at - self.starts_at != timedelta(hours=2):
            raise ValidationError("Included sessions last two hours.")
        if self.status in {self.Status.ATTENDED, self.Status.PARTIAL}:
            if (
                not self.joined_at
                or not self.left_at
                or not self.starts_at <= self.joined_at < self.left_at <= self.ends_at
            ):
                raise ValidationError("Record actual attendance within the scheduled session.")
            full = self.joined_at == self.starts_at and self.left_at == self.ends_at
            if full != (self.status == self.Status.ATTENDED):
                raise ValidationError("Use partial attendance when less than the full session was attended.")
        elif self.joined_at or self.left_at:
            raise ValidationError("Missed, cancelled and unrecorded sessions cannot have attended hours.")
        overlap = (
            SubscriptionSession.objects.filter(
                starts_at__lt=self.ends_at,
                ends_at__gt=self.starts_at,
            )
            .filter(Q(subscription__student_id=sub.student_id) | Q(tutor_id=self.tutor_id))
            .exclude(status="cancelled")
        )
        if self.status != "cancelled" and overlap.exclude(pk=self.pk).exists():
            raise ValidationError("This student or tutor already has an overlapping subscription session.")

    @property
    def attended_minutes(self):
        if self.status not in {self.Status.ATTENDED, self.Status.PARTIAL} or not self.verified_at:
            return 0
        if not self.joined_at or not self.left_at:
            return 0
        return max(0, int((self.left_at - self.joined_at).total_seconds() // 60))

    def __str__(self):
        return f"{self.subscription.reference} - {self.topic}"


class SubscriptionStudyActivity(models.Model):
    subscription = models.ForeignKey(
        "content.CurriculumSubscription", on_delete=models.PROTECT, related_name="study_activities"
    )
    enrollment = models.ForeignKey("content.Enrollment", on_delete=models.PROTECT)
    occurred_at = models.DateTimeField()
    course_title = models.CharField(max_length=200)
    lesson_title = models.CharField(max_length=200, blank=True)
    progress_percent = models.PositiveSmallIntegerField()
    kind = models.CharField(
        max_length=24, choices=[("access_started", "Course access started"), ("progress", "Progress updated")]
    )

    class Meta:
        ordering = ["occurred_at", "pk"]
        indexes = [models.Index(fields=["subscription", "occurred_at"], name="sub_activity_time_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(progress_percent__lte=100), name="sub_activity_percent_valid")
        ]


class SubscriptionReport(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Preparing"
        READY = "ready", "Ready to email"
        SENDING = "sending", "Delivery in progress - do not resend"
        SENT = "sent", "Accepted by mail provider"
        REVIEW = "review", "Delivery needs review"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.OneToOneField(
        "content.CurriculumSubscription", on_delete=models.PROTECT, related_name="final_report"
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    snapshot = models.JSONField(default=dict, editable=False)
    pdf_storage_path = models.CharField(max_length=512, blank=True, editable=False)
    pdf_sha256 = models.CharField(max_length=64, blank=True, editable=False)
    recipient = models.EmailField(blank=True, editable=False)
    generated_at = models.DateTimeField(null=True, blank=True, editable=False)
    delivery_started_at = models.DateTimeField(null=True, blank=True, editable=False)
    emailed_at = models.DateTimeField(null=True, blank=True, editable=False)
    attempts = models.PositiveSmallIntegerField(default=0, editable=False)
    next_attempt_at = models.DateTimeField(null=True, blank=True, editable=False)
    error_code = models.CharField(max_length=40, blank=True, editable=False)

    def __str__(self):
        return f"Learning report - {self.subscription.reference}"
