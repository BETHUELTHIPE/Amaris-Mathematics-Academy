import uuid
from django.db import models
from content.models import StudentRecord

class HappyForm(models.Model):
    class Service(models.TextChoices):
        LIVE_CLASS = "live_class", "Zoom online lesson"
        COURSE = "course", "Course or learning materials"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(StudentRecord, on_delete=models.PROTECT, related_name="happy_forms")
    service = models.CharField(max_length=20, choices=Service.choices)
    service_reference = models.CharField(max_length=100)
    service_title = models.CharField(max_length=200)
    tutor_name = models.CharField(max_length=160, blank=True)
    overall_rating = models.PositiveSmallIntegerField()
    tutor_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    comments = models.TextField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    archive_path = models.CharField(max_length=300, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    admin_emailed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Happy form"
        verbose_name_plural = "Happy forms"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("student", "service", "service_reference"), name="one_happy_form_per_service")
        ]

    def __str__(self):
        return f"{self.student} — {self.service_title}"

class FeedbackFollowUp(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting call"
        CONTACTED = "contacted", "Student contacted"
        RESOLVED = "resolved", "Resolved"
        UNREACHABLE = "unreachable", "Unable to reach student"

    feedback = models.OneToOneField(
        HappyForm, on_delete=models.PROTECT, related_name="followup"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    due_at = models.DateTimeField(db_index=True)
    reminder_sent_at = models.DateTimeField(blank=True, null=True)
    contacted_at = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Student follow-up"
        verbose_name_plural = "Student follow-ups"
        ordering = ("due_at",)

    def __str__(self):
        return f"Follow-up for {self.feedback.student} ({self.due_at:%Y-%m-%d})"
