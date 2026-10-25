from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import TutorApplication, TutorApplicationDocument
from .tutor_application_views import private_document_response


class QualificationInline(admin.TabularInline):
    model = TutorApplicationDocument
    fields = ("original_name", "size_bytes", "download")
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("content.view_tutorapplication") or request.user.has_perm(
            "content.change_tutorapplication"
        )

    @admin.display(description="Private qualification")
    def download(self, obj):
        url = reverse("admin:tutor-application-document", args=[obj.pk])
        return format_html('<a href="{}">Download for review</a>', url)


@admin.register(TutorApplication)
class TutorApplicationAdmin(admin.ModelAdmin):
    list_per_page = 30
    show_full_result_count = False
    list_display = ("reference", "full_name", "qualification", "status", "submitted_at", "acknowledgement_sent_at")
    list_filter = ("status", "submitted_at", "acknowledgement_sent_at")
    search_fields = ("full_name", "email", "qualification", "institution")
    readonly_fields = tuple(
        field.name for field in TutorApplication._meta.fields if field.name not in ("status", "review_notes")
    ) + ("reference",)
    inlines = (QualificationInline,)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.reviewed_by = request.user
        obj.reviewed_at = timezone.now()
        super().save_model(request, obj, form, change)
        # Recruitment review never creates a Django user or grants the Tutors group.

    def get_urls(self):
        return [
            path(
                "documents/<uuid:document_id>/",
                self.admin_site.admin_view(self.document),
                name="tutor-application-document",
            )
        ] + super().get_urls()

    def document(self, request, document_id):
        document = get_object_or_404(TutorApplicationDocument.objects.select_related("application"), pk=document_id)
        if not self.has_view_or_change_permission(request, document.application):
            raise PermissionDenied
        return private_document_response(document)


@admin.register(TutorApplicationDocument)
class TutorApplicationDocumentAdmin(admin.ModelAdmin):
    list_select_related = ("application",)
    list_display = ("original_name", "application", "size_bytes")
    readonly_fields = tuple(field.name for field in TutorApplicationDocument._meta.fields)

    def has_module_permission(self, request):
        return False  # Recruiters review documents within their parent application.

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("content.view_tutorapplication")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
