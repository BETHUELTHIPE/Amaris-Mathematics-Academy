from django.contrib import admin

from content.tutor_video_models import TutorVideoUpload


@admin.register(TutorVideoUpload)
class TutorVideoUploadAdmin(admin.ModelAdmin):
    list_display = ("id", "tutor", "video", "created_at", "delivery_status", "sent_at", "attempts", "error_code")
    list_filter = ("delivery_status",)
    search_fields = ("tutor__email", "video__title")
    list_select_related = ("tutor", "video")

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
