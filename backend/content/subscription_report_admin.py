from django.contrib import admin

from content.services.subscription_reports import save_session
from content.subscription_report_models import SubscriptionReport, SubscriptionSession, SubscriptionStudyActivity


@admin.register(SubscriptionSession)
class SubscriptionSessionAdmin(admin.ModelAdmin):
    list_display = ("subscription", "tutor", "starts_at", "topic", "status", "attended_minutes", "verified_at")
    list_filter = ("status", "subscription__curriculum")
    search_fields = ("subscription__reference", "subscription__student__email", "topic")
    autocomplete_fields = ("subscription", "tutor")
    readonly_fields = ("verified_by", "verified_at", "created_at", "updated_at", "attended_minutes")
    list_select_related = ("subscription", "tutor")

    def save_model(self, request, obj, form, change):
        save_session(obj, request.user)

    def has_delete_permission(self, request, obj=None):
        return False  # Preserve the dated ledger; record a cancellation or correction instead.


class ReadOnlyReportAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SubscriptionReport)
class SubscriptionReportAdmin(ReadOnlyReportAdmin):
    list_display = ("subscription", "status", "generated_at", "emailed_at", "attempts", "error_code")
    list_filter = ("status",)
    search_fields = ("subscription__reference", "subscription__student__email")
    list_select_related = ("subscription",)


@admin.register(SubscriptionStudyActivity)
class SubscriptionStudyActivityAdmin(ReadOnlyReportAdmin):
    list_display = ("subscription", "occurred_at", "course_title", "lesson_title", "progress_percent", "kind")
    search_fields = ("subscription__reference", "course_title")
    list_select_related = ("subscription",)
