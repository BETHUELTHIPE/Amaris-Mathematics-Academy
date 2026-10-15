from django.contrib import admin

from .models import AnnouncementMedia


class AnnouncementMediaInline(admin.TabularInline):
    model = AnnouncementMedia
    extra = 1
    fields = ("media_type", "file", "caption", "alt_text", "order")

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_add_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser
