from django.contrib import admin
from .models import HappyForm

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
