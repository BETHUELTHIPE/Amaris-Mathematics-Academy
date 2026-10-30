from django.contrib import admin
from .models import FeedbackFollowUp, HappyForm

@admin.register(HappyForm)
class HappyFormAdmin(admin.ModelAdmin):
    list_display = ("created_at", "student", "service", "service_title", "tutor_name", "overall_rating", "tutor_rating", "archived_at", "admin_emailed_at")
    list_filter = ("service", "overall_rating", "tutor_rating", "created_at")
    search_fields = ("student__email", "service_reference", "service_title", "tutor_name", "comments")
    readonly_fields = ("id", "student", "service", "service_reference", "service_title", "tutor_name", "overall_rating", "tutor_rating", "comments", "created_at", "archive_path", "archived_at", "admin_emailed_at")
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(FeedbackFollowUp)
class FeedbackFollowUpAdmin(admin.ModelAdmin):
    list_display = (
        "feedback", "due_at", "status", "contacted_at", "reminder_sent_at"
    )
    list_filter = ("status", "due_at")
    search_fields = (
        "feedback__student__email", "feedback__service_reference",
        "feedback__service_title",
    )
    readonly_fields = (
        "feedback", "due_at", "reminder_sent_at", "created_at", "updated_at"
    )
    fields = (
        "feedback", "status", "due_at", "contacted_at", "notes",
        "reminder_sent_at", "created_at", "updated_at"
    )
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
