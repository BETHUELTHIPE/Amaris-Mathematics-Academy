from botocore.exceptions import BotoCoreError, ClientError
from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from content.tutor_personnel_models import TutorPersonnelForm
from content.tutor_personnel_views import pdf_response


def is_reviewer(user):
    return user.is_superuser or (user.is_staff and not user.groups.filter(name="Tutors").exists())


@admin.register(TutorPersonnelForm)
class TutorPersonnelFormAdmin(admin.ModelAdmin):
    list_display = ("id", "tutor", "kind", "created_at", "status", "delivery_status", "sent_at")
    list_filter = ("kind", "status", "delivery_status")
    search_fields = ("id", "tutor__email", "tutor__first_name", "tutor__last_name")
    list_select_related = ("tutor", "reviewed_by")
    fields = (
        "id",
        "kind",
        "tutor",
        "created_at",
        "payload",
        "saved_form",
        "status",
        "review_notes",
        "reviewed_by",
        "reviewed_at",
        "delivery_status",
        "recipient",
        "attempts",
        "sending_at",
        "sent_at",
        "error_code",
    )

    def get_queryset(self, request):
        rows = super().get_queryset(request)
        return rows if is_reviewer(request.user) else rows.filter(tutor=request.user)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return is_reviewer(request.user) and super().has_change_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        return (
            tuple(field for field in self.fields if field not in ("status", "review_notes"))
            if self.has_change_permission(request, obj)
            else self.fields
        )

    def get_urls(self):
        return [
            path(
                "<uuid:form_id>/pdf/", self.admin_site.admin_view(self.download), name="content_tutorpersonnelform_pdf"
            )
        ] + super().get_urls()

    @admin.display(description="Original form on company letterhead")
    def saved_form(self, obj):
        return format_html(
            '<a href="{}">Download private PDF</a>', reverse("admin:content_tutorpersonnelform_pdf", args=[obj.pk])
        )

    def download(self, request, form_id):
        obj = self.get_queryset(request).filter(pk=form_id).first()
        if obj is None:
            raise Http404
        if not self.has_view_permission(request, obj):
            raise PermissionDenied
        try:
            return pdf_response(obj)
        except (ValidationError, OSError, BotoCoreError, ClientError):
            return HttpResponse(
                "The saved form is temporarily unavailable; review the private archive.",
                status=503,
                headers={"Cache-Control": "private, no-store"},
            )

    def save_model(self, request, obj, form, change):
        if not change or not self.has_change_permission(request, obj):
            raise PermissionDenied
        obj.reviewed_by, obj.reviewed_at = request.user, timezone.now()
        obj.full_clean()
        # Preserve immutable submission, PDF and outbox fields, including a worker's current delivery claim.
        obj.save(update_fields=["status", "review_notes", "reviewed_by", "reviewed_at", "updated_at"])
