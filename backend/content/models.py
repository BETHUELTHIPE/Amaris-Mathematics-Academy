import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class PublishableModel(TimeStampedModel):
    is_published = models.BooleanField(default=False, db_index=True)
    publish_at = models.DateTimeField(blank=True, null=True, db_index=True)

    class Meta:
        abstract = True

    @property
    def is_live(self) -> bool:
        return self.is_published and (self.publish_at is None or self.publish_at <= timezone.now())


class SiteSettings(TimeStampedModel):
    site_name = models.CharField(max_length=120, default="Amaris Mathematics Academy")
    short_name = models.CharField(max_length=60, default="Amaris")
    managing_director = models.CharField(max_length=120, default="Bethuel Moukangwe")
    logo = models.ImageField(upload_to="branding/", blank=True)
    favicon = models.ImageField(upload_to="branding/", blank=True)
    phone = models.CharField(max_length=30, default="071 415 6665")
    email = models.EmailField(default="bethuelmoukangwe8@gmail.com")
    address = models.TextField(default="27 Tshivhase Street, Atteridgeville, Pretoria, Gauteng, 0008")
    business_hours = models.CharField(max_length=120, default="Mon–Sun, 07:00–20:00")
    website_url = models.URLField(default="https://amaris-mathematics-academy.bethuelthipe.chatgpt.site")
    footer_description = models.TextField(
        default="Structured mathematics courses for South African school, TVET and university students."
    )
    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    youtube_url = models.URLField(blank=True)
    whatsapp_number = models.CharField(max_length=30, blank=True)
    default_meta_title = models.CharField(max_length=70, blank=True)
    default_meta_description = models.CharField(max_length=170, blank=True)
    maintenance_mode = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "Site settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.site_name


class NavigationItem(TimeStampedModel):
    class Location(models.TextChoices):
        HEADER = "header", "Header"
        FOOTER = "footer", "Footer"
        BOTH = "both", "Header and footer"

    label = models.CharField(max_length=80)
    url = models.CharField(max_length=255, help_text="Internal path or full external URL")
    location = models.CharField(max_length=12, choices=Location.choices, default=Location.HEADER)
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    open_in_new_tab = models.BooleanField(default=False)

    class Meta:
        ordering = ["location", "order", "label"]
        unique_together = [("location", "label")]
        indexes = [
            models.Index(
                fields=["location", "order"],
                condition=models.Q(is_active=True),
                name="nav_active_loc_order_idx",
            )
        ]

    def __str__(self) -> str:
        return self.label


class Page(PublishableModel):
    title = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True)
    summary = models.TextField(blank=True)
    hero_image = models.ImageField(upload_to="pages/", blank=True)
    meta_title = models.CharField(max_length=70, blank=True)
    meta_description = models.CharField(max_length=170, blank=True)
    show_in_search = models.BooleanField(default=True)
    template_key = models.CharField(max_length=60, default="standard")

    class Meta:
        ordering = ["title"]

    def __str__(self) -> str:
        return self.title


class PageSection(PublishableModel):
    page = models.ForeignKey(Page, related_name="sections", on_delete=models.CASCADE)
    section_key = models.SlugField(max_length=100)
    eyebrow = models.CharField(max_length=120, blank=True)
    heading = models.CharField(max_length=220)
    body = models.TextField(blank=True)
    image = models.ImageField(upload_to="page-sections/", blank=True)
    call_to_action_label = models.CharField(max_length=80, blank=True)
    call_to_action_url = models.CharField(max_length=255, blank=True)
    content = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured items such as statistics, cards, steps or bullet points.",
    )
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["page", "order", "id"]
        unique_together = [("page", "section_key")]
        indexes = [
            models.Index(
                fields=["page", "order"],
                condition=models.Q(is_published=True),
                name="page_section_live_idx",
            )
        ]

    def __str__(self) -> str:
        return f"{self.page}: {self.heading}"


class CourseCategory(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name_plural = "Course categories"

    def __str__(self) -> str:
        return self.name


class Course(PublishableModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        REVIEW = "review", "Ready for review"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    category = models.ForeignKey(CourseCategory, related_name="courses", on_delete=models.PROTECT)
    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200, unique=True)
    short_description = models.CharField(max_length=300)
    description = models.TextField()
    curriculum = models.CharField(max_length=100)
    academic_level = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    compare_at_price = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True, validators=[MinValueValidator(0)]
    )
    cover_image = models.ImageField(upload_to="courses/covers/", blank=True)
    outcomes = models.JSONField(default=list, blank=True)
    estimated_hours = models.PositiveIntegerField(default=0)
    featured = models.BooleanField(default=False, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "title"]
        indexes = [
            models.Index(
                fields=["order", "title"],
                condition=models.Q(status="published", is_published=True),
                name="course_live_order_idx",
            ),
            models.Index(
                fields=["order"],
                condition=models.Q(status="published", is_published=True, featured=True),
                name="course_featured_live_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        self.is_published = self.status == self.Status.PUBLISHED
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.title


class CourseModule(TimeStampedModel):
    course = models.ForeignKey(Course, related_name="modules", on_delete=models.CASCADE)
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_published = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["course", "order", "id"]
        unique_together = [("course", "order")]
        indexes = [
            models.Index(
                fields=["course", "order"],
                condition=models.Q(is_published=True),
                name="module_live_order_idx",
            )
        ]

    def __str__(self) -> str:
        return f"{self.course}: {self.title}"


class VideoAsset(PublishableModel):
    class Provider(models.TextChoices):
        YOUTUBE = "youtube", "Private YouTube"
        S3 = "s3", "Private S3 upload"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=180)
    provider = models.CharField(max_length=12, choices=Provider.choices, default=Provider.YOUTUBE)
    youtube_video_id = models.CharField(max_length=32, blank=True)
    youtube_url = models.URLField(blank=True)
    source_file = models.FileField(upload_to="videos/%Y/%m/", blank=True)
    thumbnail = models.ImageField(upload_to="videos/thumbnails/", blank=True)
    captions_file = models.FileField(upload_to="videos/captions/", blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    transcript = models.TextField(blank=True)
    allow_preview = models.BooleanField(default=False)

    class Meta:
        ordering = ["title"]

    def clean(self):
        super().clean()
        if self.provider == self.Provider.YOUTUBE:
            if not self.youtube_video_id and not self.youtube_url:
                raise ValidationError("Add a private YouTube video ID or URL.")
            if self.youtube_url and not self.youtube_video_id:
                parsed = urlparse(self.youtube_url)
                if parsed.hostname in {"youtu.be", "www.youtu.be"}:
                    self.youtube_video_id = parsed.path.strip("/")
                elif parsed.hostname in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
                    self.youtube_video_id = parse_qs(parsed.query).get("v", [""])[0]
            if not self.youtube_video_id:
                raise ValidationError("The YouTube URL does not contain a valid video ID.")
        elif not self.source_file:
            raise ValidationError("Upload a private video file for S3-hosted videos.")

    def __str__(self) -> str:
        return self.title


class Lesson(PublishableModel):
    module = models.ForeignKey(CourseModule, related_name="lessons", on_delete=models.CASCADE)
    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200)
    summary = models.TextField(blank=True)
    lesson_body = models.TextField(blank=True)
    video = models.ForeignKey(VideoAsset, related_name="lessons", on_delete=models.SET_NULL, blank=True, null=True)
    duration_minutes = models.PositiveIntegerField(default=0)
    order = models.PositiveSmallIntegerField(default=0)
    is_free_preview = models.BooleanField(default=False)

    class Meta:
        ordering = ["module", "order", "id"]
        unique_together = [("module", "slug"), ("module", "order")]
        indexes = [
            models.Index(
                fields=["module", "order", "publish_at"],
                condition=models.Q(is_published=True),
                name="lesson_live_order_idx",
            )
        ]

    def __str__(self) -> str:
        return f"{self.module}: {self.title}"


class ResourceAsset(PublishableModel):
    class ResourceType(models.TextChoices):
        WORKSHEET = "worksheet", "Worksheet"
        NOTES = "notes", "Study notes"
        PAST_PAPER = "past_paper", "Past paper"
        MEMORANDUM = "memorandum", "Memorandum"
        OTHER = "other", "Other"

    title = models.CharField(max_length=180)
    resource_type = models.CharField(max_length=20, choices=ResourceType.choices)
    file = models.FileField(upload_to="resources/%Y/%m/")
    course = models.ForeignKey(Course, related_name="resources", on_delete=models.CASCADE)
    lesson = models.ForeignKey(Lesson, related_name="resources", on_delete=models.CASCADE, blank=True, null=True)
    description = models.TextField(blank=True)
    student_download_allowed = models.BooleanField(default=True)

    class Meta:
        ordering = ["course", "title"]

    def __str__(self) -> str:
        return self.title


class PricingPlan(PublishableModel):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    billing_label = models.CharField(max_length=80, blank=True)
    features = models.JSONField(default=list, blank=True)
    call_to_action_label = models.CharField(max_length=80, default="Register first")
    call_to_action_url = models.CharField(max_length=255, default="/register")
    featured = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "price"]

    def __str__(self) -> str:
        return self.name


class Testimonial(PublishableModel):
    student_name = models.CharField(max_length=120)
    student_context = models.CharField(max_length=160, blank=True)
    quote = models.TextField()
    photo = models.ImageField(upload_to="testimonials/", blank=True)
    rating = models.PositiveSmallIntegerField(default=5, validators=[MinValueValidator(1)])
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "student_name"]

    def clean(self):
        super().clean()
        if self.rating > 5:
            raise ValidationError("Rating cannot be higher than 5.")

    def __str__(self) -> str:
        return self.student_name


class FAQ(PublishableModel):
    question = models.CharField(max_length=240)
    answer = models.TextField()
    category = models.CharField(max_length=100, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "question"]
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"

    def __str__(self) -> str:
        return self.question


class Announcement(PublishableModel):
    title = models.CharField(max_length=180)
    message = models.TextField()
    link_label = models.CharField(max_length=80, blank=True)
    link_url = models.CharField(max_length=255, blank=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    priority = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-priority", "-created_at"]
        indexes = [
            models.Index(
                fields=["-priority", "-created_at", "expires_at"],
                condition=models.Q(is_published=True),
                name="announcement_live_idx",
            )
        ]

    def __str__(self) -> str:
        return self.title


class ContactEnquiry(TimeStampedModel):
    class Status(models.TextChoices):
        NEW = "new", "New"
        IN_PROGRESS = "in_progress", "In progress"
        RESOLVED = "resolved", "Resolved"
        SPAM = "spam", "Spam"

    name = models.CharField(max_length=120)
    email = models.EmailField(unique=False)
    phone = models.CharField(max_length=30, blank=True)
    subject = models.CharField(max_length=180)
    message = models.TextField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NEW, db_index=True)
    assigned_to = models.ForeignKey(
        "auth.User", related_name="assigned_enquiries", on_delete=models.SET_NULL, blank=True, null=True
    )
    admin_notes = models.TextField(blank=True)
    resolved_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Contact enquiries"
        indexes = [models.Index(fields=["status", "-created_at"], name="enquiry_status_created_idx")]

    def __str__(self) -> str:
        return f"{self.subject} — {self.name}"


class StudentRecord(TimeStampedModel):
    supabase_user_id = models.UUIDField(unique=True, db_index=True)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    mobile = models.CharField(max_length=30, blank=True)
    institution = models.CharField(max_length=160, blank=True)
    academic_level = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name} ({self.email})"


def live_class_hold_expiry():
    return timezone.now() + timedelta(minutes=30)


class TutorAvailabilitySlot(TimeStampedModel):
    class Programme(models.TextChoices):
        CAPS = "caps", "CAPS"
        IEB = "ieb", "IEB"
        TVET = "tvet", "TVET"
        UNIVERSITY = "university", "University"

    class Subject(models.TextChoices):
        MATHEMATICS = "mathematics", "Mathematics"
        MATHEMATICAL_LITERACY = "mathematical_literacy", "Mathematical Literacy"

    tutor = models.ForeignKey(
        "auth.User",
        related_name="live_class_slots",
        on_delete=models.PROTECT,
    )
    programme = models.CharField(max_length=20, choices=Programme.choices, db_index=True)
    subject = models.CharField(max_length=32, choices=Subject.choices, db_index=True)
    level = models.CharField(max_length=80, db_index=True)
    starts_at = models.DateTimeField(db_index=True)
    ends_at = models.DateTimeField()
    zoom_join_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["starts_at", "tutor__first_name", "tutor__last_name"]
        constraints = [
            models.UniqueConstraint(
                fields=("tutor", "starts_at"),
                name="liveclass_tutor_start_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=("programme", "subject", "level", "starts_at"),
                name="liveclass_slot_lookup_idx",
            )
        ]

    def clean(self):
        super().clean()
        if self.ends_at <= self.starts_at:
            raise ValidationError("The class end time must be after the start time.")
        if self.ends_at - self.starts_at != timedelta(hours=1):
            raise ValidationError("Live class slots must be exactly one hour.")
        if self.is_active and not self.zoom_join_url:
            raise ValidationError("An active live-class slot must have a Zoom join URL.")

    @property
    def tutor_display_name(self) -> str:
        full_name = self.tutor.get_full_name().strip()
        return full_name or self.tutor.get_username()

    def __str__(self) -> str:
        return f"{self.tutor_display_name} — {self.starts_at:%Y-%m-%d %H:%M}"


class LiveClassBooking(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING_PAYMENT = "pending_payment", "Pending payment"
        CONFIRMED = "confirmed", "Confirmed"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=100, unique=True)
    idempotency_key = models.CharField(max_length=64, unique=True, editable=False)
    student = models.ForeignKey(StudentRecord, related_name="live_class_bookings", on_delete=models.PROTECT)
    slot = models.ForeignKey(TutorAvailabilitySlot, related_name="bookings", on_delete=models.PROTECT)
    programme = models.CharField(max_length=20, choices=TutorAvailabilitySlot.Programme.choices)
    subject = models.CharField(max_length=32, choices=TutorAvailabilitySlot.Subject.choices)
    level = models.CharField(max_length=80)
    topic = models.CharField(max_length=180)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default="250.00")
    currency = models.CharField(max_length=3, default="ZAR")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING_PAYMENT,
        db_index=True,
    )
    hold_expires_at = models.DateTimeField(default=live_class_hold_expiry, db_index=True)
    provider_reference = models.CharField(max_length=160, blank=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    gateway_verified_at = models.DateTimeField(blank=True, null=True)
    invoice_number = models.CharField(max_length=120, blank=True, null=True, unique=True)
    confirmation_sent_at = models.DateTimeField(blank=True, null=True)
    reminder_sent_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=("slot",),
                condition=models.Q(status__in=("pending_payment", "confirmed")),
                name="liveclass_active_slot_unique",
            )
        ]
        indexes = [
            models.Index(fields=("student", "status", "-created_at"), name="liveclass_student_status_idx"),
            models.Index(fields=("status", "hold_expires_at"), name="liveclass_hold_status_idx"),
        ]

    def __str__(self) -> str:
        return self.reference


def custom_video_attachment_upload_to(instance, filename: str) -> str:
    safe_name = Path(filename).name.replace(" ", "_")[:180] or "supporting-file"
    return f"custom-video/requests/{instance.request.reference}/{uuid.uuid4().hex}-{safe_name}"


class CustomVideoSettings(TimeStampedModel):
    enabled = models.BooleanField(
        default=False,
        help_text="Enable custom-video requests only after a flat fee has been configured.",
    )
    flat_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Admin-configured price per custom-video request. No default price is assumed.",
    )
    currency = models.CharField(max_length=3, default="ZAR")
    max_files = models.PositiveSmallIntegerField(
        default=5,
        validators=[MinValueValidator(1)],
        help_text="Maximum number of supporting files accepted per request.",
    )
    max_file_size_mb = models.PositiveSmallIntegerField(
        default=15,
        validators=[MinValueValidator(1)],
        help_text="Maximum size of each supporting file in megabytes.",
    )

    class Meta:
        verbose_name_plural = "Custom video settings"

    def clean(self):
        super().clean()
        if self.enabled and self.flat_fee is None:
            raise ValidationError("Set the custom-video flat fee before enabling requests.")

    def save(self, *args, **kwargs):
        self.pk = 1
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return "Custom video request settings"


class CustomVideoRequest(TimeStampedModel):
    class Grade(models.TextChoices):
        GRADE_10 = "10", "Grade 10"
        GRADE_11 = "11", "Grade 11"
        GRADE_12 = "12", "Grade 12"

    class Status(models.TextChoices):
        PENDING_PAYMENT = "pending_payment", "Pending payment"
        PAID = "paid", "Paid"
        IN_PROGRESS = "in_progress", "In progress"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=100, unique=True)
    idempotency_key = models.CharField(max_length=64, unique=True, editable=False)
    student = models.ForeignKey(
        StudentRecord,
        related_name="custom_video_requests",
        on_delete=models.PROTECT,
    )
    curriculum = models.CharField(
        max_length=20,
        choices=TutorAvailabilitySlot.Programme.choices,
        db_index=True,
    )
    subject = models.CharField(
        max_length=32,
        choices=TutorAvailabilitySlot.Subject.choices,
        db_index=True,
    )
    grade = models.CharField(max_length=2, choices=Grade.choices, db_index=True)
    topic = models.CharField(max_length=220)
    amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    currency = models.CharField(max_length=3, default="ZAR")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING_PAYMENT,
        db_index=True,
    )
    provider_reference = models.CharField(max_length=160, blank=True)
    gateway_verified_at = models.DateTimeField(blank=True, null=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    invoice_sent_at = models.DateTimeField(blank=True, null=True)
    delivery_url = models.URLField(blank=True)
    admin_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=("provider_reference",),
                condition=~models.Q(provider_reference=""),
                name="custom_video_provider_ref_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=("student", "status", "-created_at"),
                name="custom_video_student_status_idx",
            )
        ]

    def __str__(self) -> str:
        return self.reference


class CustomVideoRequestAttachment(TimeStampedModel):
    request = models.ForeignKey(
        CustomVideoRequest,
        related_name="attachments",
        on_delete=models.CASCADE,
    )
    file = models.FileField(upload_to=custom_video_attachment_upload_to)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.PositiveBigIntegerField()

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"{self.request.reference} — {self.original_name}"


class CustomVideoInvoice(TimeStampedModel):
    request = models.OneToOneField(
        CustomVideoRequest,
        related_name="invoice",
        on_delete=models.PROTECT,
    )
    invoice_number = models.CharField(max_length=120, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="ZAR")
    issued_at = models.DateTimeField(default=timezone.now)
    pdf_file = models.FileField(
        upload_to="custom-video/invoices/%Y/%m/",
        blank=True,
    )

    class Meta:
        ordering = ["-issued_at"]

    def __str__(self) -> str:
        return self.invoice_number


class Enrollment(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending payment"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    student = models.ForeignKey(StudentRecord, related_name="enrollments", on_delete=models.PROTECT)
    course = models.ForeignKey(Course, related_name="enrollments", on_delete=models.PROTECT)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    progress_percent = models.PositiveSmallIntegerField(default=0)
    last_lesson = models.ForeignKey(
        Lesson,
        related_name="last_resumed_enrollments",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    last_position_seconds = models.PositiveIntegerField(default=0)
    progress_updated_at = models.DateTimeField(blank=True, null=True)
    enrolled_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-enrolled_at"]
        unique_together = [("student", "course")]
        indexes = [models.Index(fields=["student", "status", "-enrolled_at"], name="enrol_student_status_idx")]

    def clean(self):
        super().clean()
        if self.progress_percent > 100:
            raise ValidationError("Progress cannot be higher than 100%.")
        last_lesson = self.last_lesson
        if last_lesson is not None and last_lesson.module.course_id != self.course_id:
            raise ValidationError("The resume lesson must belong to the enrollment course.")

    def __str__(self) -> str:
        return f"{self.student} — {self.course}"


class Payment(TimeStampedModel):
    class Provider(models.TextChoices):
        PAYFAST = "payfast", "PayFast"
        GOOGLE_PAY = "google_pay", "Google Pay"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    reference = models.CharField(max_length=100, unique=True)
    student = models.ForeignKey(StudentRecord, related_name="payments", on_delete=models.PROTECT)
    course = models.ForeignKey(Course, related_name="payments", on_delete=models.PROTECT)
    enrollment = models.ForeignKey(
        Enrollment, related_name="payments", on_delete=models.SET_NULL, blank=True, null=True
    )
    provider = models.CharField(max_length=16, choices=Provider.choices)
    provider_reference = models.CharField(max_length=160, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, default="ZAR")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    gateway_verified_at = models.DateTimeField(
        blank=True,
        null=True,
        db_index=True,
        help_text="Set only after server-side gateway verification succeeds.",
    )
    verification_source = models.CharField(
        max_length=40,
        blank=True,
        editable=False,
        help_text="Opaque verification method identifier; never store credentials here.",
    )
    raw_response = models.JSONField(default=dict, blank=True, editable=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["created_at"],
                condition=models.Q(status="paid", gateway_verified_at__isnull=False, enrollment__isnull=True),
                name="payment_reconcile_idx",
            ),
            models.Index(fields=["student", "status", "-created_at"], name="payment_student_status_idx"),
        ]

    def __str__(self) -> str:
        return self.reference


class PaymentReconciliationRun(TimeStampedModel):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RUNNING, db_index=True)
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    payments_scanned = models.PositiveIntegerField(default=0)
    enrollments_repaired = models.PositiveIntegerField(default=0)
    unresolved_count = models.PositiveIntegerField(default=0)
    error_code = models.CharField(
        max_length=120,
        blank=True,
        editable=False,
        help_text="Non-sensitive exception class or operational code only.",
    )

    class Meta:
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["status", "-started_at"], name="reconcile_status_time_idx")]

    def __str__(self) -> str:
        return f"{self.started_at:%Y-%m-%d %H:%M} — {self.status}"
