from django.contrib import admin, messages
from django.utils import timezone

from .models import (
    FAQ,
    Announcement,
    ContactEnquiry,
    CustomVideoInvoice,
    CustomVideoRequest,
    CustomVideoRequestAttachment,
    CustomVideoSettings,
    Course,
    CourseCategory,
    CourseModule,
    Enrollment,
    Lesson,
    LiveClassBooking,
    NavigationItem,
    Page,
    PageSection,
    Payment,
    PaymentReconciliationRun,
    PricingPlan,
    ResourceAsset,
    SiteSettings,
    StudentRecord,
    Testimonial,
    TutorAvailabilitySlot,
    VideoAsset,
)

admin.site.site_header = "Amaris Mathematics Academy"
admin.site.site_title = "Amaris Academy Admin"
admin.site.index_title = "Content and learning operations"


class TimeStampedAdmin(admin.ModelAdmin):
    readonly_fields = ("created_at", "updated_at")
    list_per_page = 30
    save_on_top = True


class PublishableAdmin(TimeStampedAdmin):
    list_filter = ("is_published", "publish_at")
    actions = ("publish_selected", "unpublish_selected")

    @admin.action(description="Publish selected items now")
    def publish_selected(self, request, queryset):
        updated = queryset.update(is_published=True, publish_at=timezone.now())
        self.message_user(request, f"Published {updated} item(s).", messages.SUCCESS)

    @admin.action(description="Unpublish selected items")
    def unpublish_selected(self, request, queryset):
        updated = queryset.update(is_published=False)
        self.message_user(request, f"Unpublished {updated} item(s).", messages.SUCCESS)


@admin.register(SiteSettings)
class SiteSettingsAdmin(TimeStampedAdmin):
    fieldsets = (
        ("Brand", {"fields": ("site_name", "short_name", "managing_director", "logo", "favicon")}),
        ("Contact", {"fields": ("phone", "email", "address", "business_hours", "website_url", "whatsapp_number")}),
        (
            "Website",
            {"fields": ("footer_description", "default_meta_title", "default_meta_description", "maintenance_mode")},
        ),
        ("Social media", {"fields": ("facebook_url", "instagram_url", "youtube_url")}),
        ("Audit", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(NavigationItem)
class NavigationItemAdmin(TimeStampedAdmin):
    list_display = ("label", "url", "location", "order", "is_active")
    list_editable = ("order", "is_active")
    list_filter = ("location", "is_active")
    search_fields = ("label", "url")


class PageSectionInline(admin.StackedInline):
    model = PageSection
    extra = 0
    fields = (
        "section_key",
        "eyebrow",
        "heading",
        "body",
        "image",
        "call_to_action_label",
        "call_to_action_url",
        "content",
        "order",
        "is_published",
        "publish_at",
    )
    ordering = ("order",)


@admin.register(Page)
class PageAdmin(PublishableAdmin):
    list_display = ("title", "slug", "template_key", "is_published", "publish_at", "updated_at")
    list_filter = PublishableAdmin.list_filter + ("template_key", "show_in_search")
    search_fields = ("title", "slug", "summary", "meta_title")
    prepopulated_fields = {"slug": ("title",)}
    inlines = (PageSectionInline,)


@admin.register(PageSection)
class PageSectionAdmin(PublishableAdmin):
    list_display = ("heading", "page", "section_key", "order", "is_published", "updated_at")
    list_filter = PublishableAdmin.list_filter + ("page",)
    list_editable = ("order", "is_published")
    search_fields = ("heading", "eyebrow", "body", "section_key")
    autocomplete_fields = ("page",)


@admin.register(CourseCategory)
class CourseCategoryAdmin(TimeStampedAdmin):
    list_display = ("name", "slug", "order", "is_active", "updated_at")
    list_editable = ("order", "is_active")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}


class CourseModuleInline(admin.TabularInline):
    model = CourseModule
    extra = 0
    fields = ("title", "description", "order", "is_published")
    ordering = ("order",)


class CourseResourceInline(admin.TabularInline):
    model = ResourceAsset
    extra = 0
    fields = ("title", "resource_type", "file", "is_published", "student_download_allowed")


@admin.register(Course)
class CourseAdmin(PublishableAdmin):
    list_display = (
        "title",
        "category",
        "curriculum",
        "academic_level",
        "price",
        "status",
        "featured",
        "updated_at",
    )
    list_filter = ("status", "featured", "category", "curriculum", "academic_level")
    list_editable = ("status", "featured")
    search_fields = ("title", "slug", "short_description", "description", "curriculum")
    prepopulated_fields = {"slug": ("title",)}
    autocomplete_fields = ("category",)
    inlines = (CourseModuleInline, CourseResourceInline)
    fieldsets = (
        ("Course", {"fields": ("category", "title", "slug", "short_description", "description")}),
        ("Academic details", {"fields": ("curriculum", "academic_level", "outcomes", "estimated_hours")}),
        ("Price and artwork", {"fields": ("price", "compare_at_price", "cover_image")}),
        ("Publishing", {"fields": ("status", "featured", "order", "publish_at")}),
        ("Audit", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.action(description="Publish selected courses now")
    def publish_selected(self, request, queryset):
        updated = queryset.update(
            status=Course.Status.PUBLISHED,
            is_published=True,
            publish_at=timezone.now(),
        )
        self.message_user(request, f"Published {updated} course(s).", messages.SUCCESS)

    @admin.action(description="Return selected courses to draft")
    def unpublish_selected(self, request, queryset):
        updated = queryset.update(status=Course.Status.DRAFT, is_published=False)
        self.message_user(request, f"Moved {updated} course(s) to draft.", messages.SUCCESS)


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 0
    fields = ("title", "slug", "video", "duration_minutes", "order", "is_published", "is_free_preview")
    ordering = ("order",)
    autocomplete_fields = ("video",)


@admin.register(CourseModule)
class CourseModuleAdmin(TimeStampedAdmin):
    list_display = ("title", "course", "order", "is_published", "updated_at")
    list_filter = ("is_published", "course")
    list_editable = ("order", "is_published")
    search_fields = ("title", "description", "course__title")
    autocomplete_fields = ("course",)
    inlines = (LessonInline,)


@admin.register(Lesson)
class LessonAdmin(PublishableAdmin):
    list_display = ("title", "module", "order", "duration_minutes", "is_free_preview", "is_published")
    list_filter = PublishableAdmin.list_filter + ("is_free_preview", "module__course")
    list_editable = ("order", "is_free_preview", "is_published")
    search_fields = ("title", "summary", "lesson_body", "module__title", "module__course__title")
    prepopulated_fields = {"slug": ("title",)}
    autocomplete_fields = ("module", "video")


@admin.register(VideoAsset)
class VideoAssetAdmin(PublishableAdmin):
    list_display = ("title", "provider", "duration_seconds", "allow_preview", "is_published", "updated_at")
    list_filter = PublishableAdmin.list_filter + ("provider", "allow_preview")
    list_editable = ("allow_preview", "is_published")
    search_fields = ("title", "youtube_video_id", "youtube_url", "transcript")
    readonly_fields = ("id", "created_at", "updated_at")
    fieldsets = (
        ("Video", {"fields": ("id", "title", "provider", "duration_seconds", "thumbnail")}),
        ("Private YouTube", {"fields": ("youtube_video_id", "youtube_url")}),
        ("Private S3 upload", {"fields": ("source_file", "captions_file")}),
        ("Learning content", {"fields": ("transcript", "allow_preview")}),
        ("Publishing", {"fields": ("is_published", "publish_at")}),
        ("Audit", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )


@admin.register(ResourceAsset)
class ResourceAssetAdmin(PublishableAdmin):
    list_display = ("title", "resource_type", "course", "lesson", "student_download_allowed", "is_published")
    list_filter = PublishableAdmin.list_filter + ("resource_type", "student_download_allowed", "course")
    search_fields = ("title", "description", "course__title", "lesson__title")
    autocomplete_fields = ("course", "lesson")


@admin.register(PricingPlan)
class PricingPlanAdmin(PublishableAdmin):
    list_display = ("name", "price", "billing_label", "featured", "order", "is_published")
    list_editable = ("featured", "order", "is_published")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Testimonial)
class TestimonialAdmin(PublishableAdmin):
    list_display = ("student_name", "student_context", "rating", "order", "is_published")
    list_editable = ("order", "is_published")
    search_fields = ("student_name", "student_context", "quote")


@admin.register(FAQ)
class FAQAdmin(PublishableAdmin):
    list_display = ("question", "category", "order", "is_published")
    list_filter = PublishableAdmin.list_filter + ("category",)
    list_editable = ("order", "is_published")
    search_fields = ("question", "answer", "category")


@admin.register(Announcement)
class AnnouncementAdmin(PublishableAdmin):
    list_display = ("title", "priority", "expires_at", "is_published", "updated_at")
    list_editable = ("priority", "is_published")
    search_fields = ("title", "message")


@admin.register(ContactEnquiry)
class ContactEnquiryAdmin(TimeStampedAdmin):
    list_display = ("subject", "name", "email", "status", "assigned_to", "created_at")
    list_filter = ("status", "created_at", "assigned_to")
    list_editable = ("status", "assigned_to")
    search_fields = ("name", "email", "phone", "subject", "message")
    readonly_fields = ("name", "email", "phone", "subject", "message", "created_at", "updated_at")
    actions = ("mark_in_progress", "mark_resolved")
    date_hierarchy = "created_at"

    @admin.action(description="Mark selected enquiries in progress")
    def mark_in_progress(self, request, queryset):
        queryset.update(status=ContactEnquiry.Status.IN_PROGRESS)

    @admin.action(description="Mark selected enquiries resolved")
    def mark_resolved(self, request, queryset):
        queryset.update(status=ContactEnquiry.Status.RESOLVED, resolved_at=timezone.now())


@admin.register(CustomVideoSettings)
class CustomVideoSettingsAdmin(TimeStampedAdmin):
    list_display = (
        "enabled",
        "flat_fee",
        "currency",
        "max_files",
        "max_file_size_mb",
        "updated_at",
    )
    fieldsets = (
        (
            "Availability and pricing",
            {
                "fields": (
                    "enabled",
                    "flat_fee",
                    "currency",
                    "max_files",
                    "max_file_size_mb",
                )
            },
        ),
        ("Audit", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def has_add_permission(self, request):
        return not CustomVideoSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


class CustomVideoAttachmentInline(admin.TabularInline):
    model = CustomVideoRequestAttachment
    extra = 0
    fields = (
        "original_name",
        "content_type",
        "size_bytes",
        "file",
        "created_at",
    )
    readonly_fields = fields
    can_delete = False


@admin.register(CustomVideoRequest)
class CustomVideoRequestAdmin(TimeStampedAdmin):
    list_display = (
        "reference",
        "student",
        "curriculum",
        "subject",
        "grade",
        "topic",
        "amount",
        "status",
        "paid_at",
        "invoice_sent_at",
    )
    list_filter = ("status", "curriculum", "subject", "grade", "created_at")
    search_fields = (
        "reference",
        "student__email",
        "student__first_name",
        "student__last_name",
        "topic",
        "provider_reference",
    )
    list_editable = ("status",)
    readonly_fields = (
        "id",
        "reference",
        "idempotency_key",
        "student",
        "curriculum",
        "subject",
        "grade",
        "topic",
        "amount",
        "currency",
        "provider_reference",
        "gateway_verified_at",
        "paid_at",
        "invoice_sent_at",
        "created_at",
        "updated_at",
    )
    inlines = (CustomVideoAttachmentInline,)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CustomVideoInvoice)
class CustomVideoInvoiceAdmin(TimeStampedAdmin):
    list_display = ("invoice_number", "request", "amount", "currency", "issued_at")
    search_fields = (
        "invoice_number",
        "request__reference",
        "request__student__email",
    )
    readonly_fields = (
        "request",
        "invoice_number",
        "amount",
        "currency",
        "issued_at",
        "pdf_file",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class EnrollmentInline(admin.TabularInline):
    model = Enrollment
    extra = 0
    fields = ("course", "status", "progress_percent", "enrolled_at", "completed_at")
    readonly_fields = ("enrolled_at",)


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    fields = ("reference", "course", "provider", "amount", "currency", "status", "paid_at")
    readonly_fields = ("reference", "course", "provider", "amount", "currency", "status", "paid_at")
    can_delete = False


@admin.register(StudentRecord)
class StudentRecordAdmin(TimeStampedAdmin):
    list_display = ("email", "first_name", "last_name", "academic_level", "institution", "is_active")
    list_filter = ("is_active", "academic_level", "institution")
    list_editable = ("is_active",)
    search_fields = ("email", "first_name", "last_name", "mobile", "institution", "supabase_user_id")
    readonly_fields = ("supabase_user_id", "email", "created_at", "updated_at")
    inlines = (EnrollmentInline, PaymentInline)

    def has_add_permission(self, request):
        return False


@admin.register(Enrollment)
class EnrollmentAdmin(TimeStampedAdmin):
    list_display = ("student", "course", "status", "progress_percent", "enrolled_at")
    list_filter = ("status", "course", "enrolled_at")
    search_fields = ("student__email", "student__first_name", "student__last_name", "course__title")
    autocomplete_fields = ("student", "course")
    readonly_fields = ("enrolled_at", "created_at", "updated_at")


@admin.register(Payment)
class PaymentAdmin(TimeStampedAdmin):
    list_display = (
        "reference",
        "student",
        "course",
        "provider",
        "amount",
        "currency",
        "status",
        "gateway_verified_at",
    )
    list_filter = ("status", "provider", "currency", "gateway_verified_at", "paid_at", "created_at")
    search_fields = ("reference", "provider_reference", "student__email", "course__title")
    autocomplete_fields = ("student", "course", "enrollment")
    readonly_fields = (
        "reference",
        "student",
        "course",
        "enrollment",
        "provider",
        "provider_reference",
        "amount",
        "currency",
        "status",
        "paid_at",
        "gateway_verified_at",
        "verification_source",
        "raw_response",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentReconciliationRun)
class PaymentReconciliationRunAdmin(TimeStampedAdmin):
    list_display = (
        "started_at",
        "status",
        "payments_scanned",
        "enrollments_repaired",
        "unresolved_count",
        "completed_at",
    )
    list_filter = ("status", "started_at")
    readonly_fields = (
        "id",
        "status",
        "started_at",
        "completed_at",
        "payments_scanned",
        "enrollments_repaired",
        "unresolved_count",
        "error_code",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in ("GET", "HEAD", "OPTIONS")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TutorAvailabilitySlot)
class TutorAvailabilitySlotAdmin(TimeStampedAdmin):
    list_display = (
        "tutor",
        "programme",
        "subject",
        "level",
        "starts_at",
        "ends_at",
        "is_active",
    )
    list_filter = ("programme", "subject", "level", "is_active", "starts_at")
    search_fields = (
        "tutor__username",
        "tutor__first_name",
        "tutor__last_name",
        "level",
    )
    autocomplete_fields = ("tutor",)
    list_editable = ("is_active",)
    ordering = ("starts_at",)


@admin.register(LiveClassBooking)
class LiveClassBookingAdmin(TimeStampedAdmin):
    list_display = (
        "reference",
        "student",
        "slot",
        "topic",
        "amount",
        "status",
        "paid_at",
        "confirmation_sent_at",
        "reminder_sent_at",
    )
    list_filter = ("status", "programme", "subject", "slot__starts_at")
    search_fields = (
        "reference",
        "student__email",
        "student__first_name",
        "student__last_name",
        "topic",
        "invoice_number",
    )
    readonly_fields = (
        "id",
        "reference",
        "idempotency_key",
        "student",
        "slot",
        "programme",
        "subject",
        "level",
        "topic",
        "amount",
        "currency",
        "status",
        "hold_expires_at",
        "provider_reference",
        "paid_at",
        "gateway_verified_at",
        "invoice_number",
        "confirmation_sent_at",
        "reminder_sent_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
