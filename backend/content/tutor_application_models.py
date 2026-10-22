"""Recruitment records are separate from approved tutor permissions."""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class TutorApplication(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Application received"
        REVIEWING = "reviewing", "Under review"
        SHORTLISTED = "shortlisted", "Shortlisted"
        CLOSED = "closed", "Review completed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supabase_user_id = models.UUIDField(unique=True, editable=False)
    email = models.EmailField(editable=False)
    full_name = models.CharField(max_length=160)
    phone = models.CharField(max_length=30)
    location = models.CharField(max_length=500)
    country = models.CharField(max_length=2, blank=True, default="")
    province = models.CharField(max_length=160, blank=True, default="")
    city = models.CharField(max_length=160, blank=True, default="")
    qualification = models.CharField(max_length=200)
    institution = models.CharField(max_length=200)
    subjects = models.CharField(max_length=300)
    programmes = models.JSONField(default=list)
    levels = models.CharField(max_length=200)
    experience_years = models.PositiveSmallIntegerField(default=0)
    teaching_experience = models.TextField()
    availability = models.TextField()
    motivation = models.TextField()
    consented_at = models.DateTimeField(default=timezone.now, editable=False)
    submitted_at = models.DateTimeField(default=timezone.now, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SUBMITTED)
    review_notes = models.TextField(blank=True, help_text="Internal recruitment notes; never shown to applicants.")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    acknowledgement_sent_at = models.DateTimeField(null=True, blank=True, editable=False)
    acknowledgement_attempts = models.PositiveIntegerField(default=0, editable=False)
    acknowledgement_next_attempt_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    acknowledgement_error = models.CharField(max_length=120, blank=True, editable=False)

    class Meta:
        ordering = ["-submitted_at"]

    @property
    def reference(self):
        return f"AMARIS-TUTOR-{self.id.hex[:12].upper()}"

    def __str__(self):
        return self.reference


class TutorApplicationDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(TutorApplication, related_name="documents", on_delete=models.CASCADE)
    storage_path = models.CharField(max_length=512, editable=False)
    original_name = models.CharField(max_length=200)
    content_type = models.CharField(max_length=80)
    size_bytes = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64, editable=False)

    def __str__(self):
        return self.original_name
