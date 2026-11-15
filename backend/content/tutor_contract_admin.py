from botocore.exceptions import BotoCoreError, ClientError
from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponse
from django.urls import path, reverse
from django.utils.html import format_html

from content.services.tutor_contracts import countersign_contract, decline_contract
from content.tutor_contract_models import TutorEmploymentContract
from content.tutor_contract_views import pdf_response


@admin.register(TutorEmploymentContract)
class TutorEmploymentContractAdmin(admin.ModelAdmin):
    list_display = ("id", "tutor", "created_at", "status", "delivery_status", "sent_at")
    list_filter = ("status", "delivery_status", "terms_version")
    search_fields = ("id", "tutor__email", "tutor__first_name", "tutor__last_name")
    list_select_related = ("tutor", "reviewed_by")
    fields = (
        "id",
        "tutor",
        "created_at",
        "terms_version",
        "payload",
        "service_terms",
        "statutory_hourly_floor",
        "saved_contract",
        "status",
        "review_notes",
        "employer_signature_name",
        "effective_date",
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
        return rows if request.user.is_superuser else rows.none()

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_readonly_fields(self, request, obj=None):
        mutable = ("status", "review_notes", "employer_signature_name", "effective_date")
        if obj and obj.status != TutorEmploymentContract.Status.SUBMITTED:
            mutable = ()
        return tuple(field for field in self.fields if field not in mutable)

    def get_urls(self):
        return [
            path(
                "<uuid:contract_id>/pdf/",
                self.admin_site.admin_view(self.download),
                name="content_tutoremploymentcontract_pdf",
            )
        ] + super().get_urls()

    @admin.display(description="Private signed contract")
    def saved_contract(self, obj):
        label = "Download executed PDF" if obj.executed_pdf else "Download tutor-signed PDF"
        return format_html(
            '<a href="{}">{}</a>', reverse("admin:content_tutoremploymentcontract_pdf", args=[obj.pk]), label
        )

    def download(self, request, contract_id):
        obj = self.get_queryset(request).filter(pk=contract_id).first()
        if obj is None:
            raise Http404
        if not self.has_view_permission(request, obj):
            raise PermissionDenied
        try:
            return pdf_response(obj)
        except (ValidationError, OSError, BotoCoreError, ClientError):
            return HttpResponse(
                "The saved contract is temporarily unavailable; review the private archive.",
                status=503,
                headers={"Cache-Control": "private, no-store"},
            )

    def save_model(self, request, obj, form, change):
        if not change or not request.user.is_superuser:
            raise PermissionDenied
        if obj.status == TutorEmploymentContract.Status.ACCEPTED:
            countersign_contract(obj, reviewer=request.user)
        elif obj.status == TutorEmploymentContract.Status.DECLINED:
            decline_contract(obj, reviewer=request.user)
        else:
            raise ValidationError("Choose Accepted or Declined to complete the review.")
