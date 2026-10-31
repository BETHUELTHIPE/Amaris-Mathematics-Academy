from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html

from .library_models import LibraryResource
from .library_views import LibraryDownloadView


@admin.register(LibraryResource)
class LibraryResourceAdmin(admin.ModelAdmin):
    list_display = ("title", "resource_type", "subject", "level", "is_published", "uploaded_by", "created_at")
    list_filter = ("resource_type", "is_published", "subject")
    search_fields = ("title", "description", "subject", "level", "original_name")
    readonly_fields = (
        "uploaded_by",
        "original_name",
        "size_bytes",
        "content_type",
        "created_at",
        "updated_at",
        "download",
    )
    fields = (
        "title",
        "description",
        "resource_type",
        "subject",
        "level",
        "file",
        "sharing_permitted",
        "is_published",
        "download",
        "uploaded_by",
        "original_name",
        "size_bytes",
        "content_type",
        "created_at",
        "updated_at",
    )
    list_per_page = 30

    def save_model(self, request, obj, form, change):
        if not change:
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)

    def get_urls(self):
        return [
            path(
                "<uuid:resource_id>/download/",
                self.admin_site.admin_view(self.download_file),
                name="content_libraryresource_download",
            )
        ] + super().get_urls()

    @admin.display(description="Download")
    def download(self, obj):
        if not obj.pk or not obj.file:
            return "Save the document to download it."
        return format_html(
            '<a href="{}">Download document</a>', reverse("admin:content_libraryresource_download", args=[obj.pk])
        )

    def download_file(self, request, resource_id):
        resource = get_object_or_404(LibraryResource, pk=resource_id)
        if not self.has_view_or_change_permission(request, resource):
            raise PermissionDenied
        view = LibraryDownloadView()
        view.visible_resources = lambda: LibraryResource.objects.all()
        response = view.get(request, resource_id)
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
