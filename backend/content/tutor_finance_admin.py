"""Superuser-only financial controls. Raw account numbers are write-only and encrypted."""

import re

from cryptography.fernet import Fernet
from django import forms
from django.conf import settings
from django.contrib import admin
from django.core.exceptions import ValidationError

from .tutor_finance_models import (
    TutorContract,
    TutorCourseAssignment,
    TutorEarning,
    TutorPaymentProfile,
    TutorPayout,
    TutorActivityStatement,
)


class FinanceSuperuserAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return bool(request.user.is_active and request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return bool(request.user.is_active and request.user.is_superuser)

    def has_add_permission(self, request):
        return bool(request.user.is_active and request.user.is_superuser)

    def has_change_permission(self, request, obj=None):
        return bool(request.user.is_active and request.user.is_superuser)

    def has_delete_permission(self, request, obj=None):
        return False


def encrypt_bank_account(value):
    key = getattr(settings, "TUTOR_BANK_FERNET_KEY", "")
    if not key:
        raise ValidationError("TUTOR_BANK_FERNET_KEY must be securely configured before entering bank details.")
    try:
        return Fernet(key.encode()).encrypt(value.encode()).decode()
    except (ValueError, TypeError) as exc:
        raise ValidationError("The encrypted bank-account vault is not configured correctly.") from exc


class TutorPaymentProfileForm(forms.ModelForm):
    account_number = forms.CharField(
        required=False,
        min_length=6,
        max_length=20,
        label="New bank account number (write-only)",
        help_text="Leave blank to retain existing encrypted details. Never share it in email or logs.",
        widget=forms.PasswordInput(render_value=False),
    )

    class Meta:
        model = TutorPaymentProfile
        fields = ("tutor", "account_holder", "bank_name", "branch_code", "is_active")

    def clean_account_number(self):
        number = self.cleaned_data.get("account_number", "").strip().replace(" ", "")
        if number and not re.fullmatch(r"[0-9]{6,20}", number):
            raise ValidationError("Enter 6–20 digits without punctuation.")
        return number

    def clean(self):
        cleaned = super().clean()
        number = cleaned.get("account_number")
        if number:
            self.instance.encrypted_account_number = encrypt_bank_account(number)
            self.instance.account_last_four = number[-4:]
            # Any changed bank account must undergo ownership verification again.
            self.instance.recipient_verified_at = None
            self.instance.provider_recipient_id = ""
            self.instance.is_active = False
            cleaned["is_active"] = False
        return cleaned


@admin.register(TutorPaymentProfile)
class TutorPaymentProfileAdmin(FinanceSuperuserAdmin):
    form = TutorPaymentProfileForm
    list_display = ("tutor", "bank_name", "masked_account", "is_active", "recipient_verified_at")
    search_fields = ("tutor__username", "tutor__email", "bank_name")
    autocomplete_fields = ("tutor",)
    readonly_fields = ("masked_account", "recipient_verified_at", "created_at", "updated_at")
    fields = (
        "tutor",
        "account_holder",
        "bank_name",
        "branch_code",
        "account_number",
        "masked_account",
        "is_active",
        "recipient_verified_at",
        "created_at",
        "updated_at",
    )

    @admin.display(description="Account")
    def masked_account(self, obj):
        return f"•••• {obj.account_last_four}" if obj.account_last_four else "Not configured"

    def save_model(self, request, obj, form, change):
        if not getattr(settings, "TUTOR_BANK_FERNET_KEY", "") and form.cleaned_data.get("account_number"):
            raise ValidationError("Configure the account encryption key first.")
        super().save_model(request, obj, form, change)


@admin.register(TutorContract)
class TutorContractAdmin(FinanceSuperuserAdmin):
    list_display = (
        "tutor",
        "service",
        "tutor_percent",
        "academy_percent",
        "contract_reference",
        "effective_from",
        "is_active",
    )
    autocomplete_fields = ("tutor",)
    list_filter = ("service", "is_active")
    search_fields = ("tutor__username", "contract_reference")

    @admin.display(description="Amaris share")
    def academy_percent(self, obj):
        return f"{100 - obj.tutor_percent}%"


@admin.register(TutorCourseAssignment)
class TutorCourseAssignmentAdmin(FinanceSuperuserAdmin):
    list_display = ("course", "tutor", "is_active")
    autocomplete_fields = ("course", "tutor")


@admin.register(TutorEarning)
class TutorEarningAdmin(FinanceSuperuserAdmin):
    list_display = (
        "tutor",
        "service",
        "service_label",
        "gross",
        "tutor_percent",
        "tutor_amount",
        "academy_amount",
        "state",
    )
    list_filter = ("service", "state", "payment_verified_at")
    search_fields = ("source_reference", "tutor__username")
    readonly_fields = [field.name for field in TutorEarning._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(TutorPayout)
class TutorPayoutAdmin(FinanceSuperuserAdmin):
    list_display = ("earning", "state", "provider_name", "provider_reference", "confirmed_at", "receipt_emailed_at")
    list_filter = ("state",)
    readonly_fields = [field.name for field in TutorPayout._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(TutorActivityStatement)
class TutorActivityStatementAdmin(FinanceSuperuserAdmin):
    """Only Django superusers can list, inspect or download private statements."""

    list_display = (
        "report_number",
        "tutor",
        "period_start",
        "period_end",
        "sessions_taught",
        "video_requests",
        "tutor_share",
        "state",
        "tutor_emailed_at",
        "admin_emailed_at",
        "download",
    )
    list_filter = ("state", "period_end", "tutor_emailed_at", "admin_emailed_at")
    search_fields = ("report_number", "tutor__username", "tutor__email")
    list_select_related = ("tutor",)
    readonly_fields = (
        "report_number",
        "tutor",
        "period_start",
        "period_end",
        "state",
        "activity_overview",
        "financial_overview",
        "pdf_sha256",
        "download",
        "tutor_emailed_at",
        "admin_emailed_at",
        "created_at",
        "updated_at",
    )
    fields = readonly_fields
    list_per_page = 30
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def sessions_taught(self, obj):
        return obj.snapshot.get("sessions_taught", 0)

    def video_requests(self, obj):
        return obj.snapshot.get("video_requests", 0)

    def tutor_share(self, obj):
        return f"R {obj.snapshot.get('tutor_share', '0.00')}"

    @admin.display(description="Activities")
    def activity_overview(self, obj):
        d = obj.snapshot
        return (
            f"Students served: {d.get('unique_students', 0)}; "
            f"completed classes: {d.get('sessions_taught', 0)}; "
            f"teaching hours: {d.get('hours_taught', 0)}; "
            f"video requests: {d.get('video_requests', 0)}; "
            f"ready videos: {d.get('videos_delivered', 0)}"
        )

    @admin.display(description="Finance")
    def financial_overview(self, obj):
        d = obj.snapshot
        return (
            f"Verified gross: R {d.get('gross_verified', '0.00')}; "
            f"tutor share: R {d.get('tutor_share', '0.00')}; "
            f"held: R {d.get('held_earnings', '0.00')}; "
            f"eligible: R {d.get('ready_earnings', '0.00')}; "
            f"provider-confirmed payout: R {d.get('confirmed_payouts_in_period', '0.00')}"
        )

    @admin.display(description="PDF report")
    def download(self, obj):
        if not obj or not obj.pdf_storage_path:
            return "Archive pending"
        from django.urls import reverse
        from django.utils.html import format_html

        link = reverse("admin:content_tutoractivitystatement_download", args=[obj.pk])
        return format_html('<a href="{}">Download private statement</a>', link)

    def get_urls(self):
        from django.urls import path

        return [
            path(
                "<int:object_id>/download/",
                self.admin_site.admin_view(self.download_report),
                name="content_tutoractivitystatement_download",
            )
        ] + super().get_urls()

    def download_report(self, request, object_id):
        from django.core.exceptions import PermissionDenied
        from django.core.files.storage import storages
        from django.http import FileResponse
        from django.shortcuts import get_object_or_404

        if not self.has_view_permission(request):
            raise PermissionDenied()
        statement = get_object_or_404(TutorActivityStatement, pk=object_id)
        if not statement.pdf_storage_path:
            raise PermissionDenied()
        stream = storages["default"].open(statement.pdf_storage_path, "rb")
        response = FileResponse(
            stream, content_type="application/pdf", as_attachment=True, filename=f"{statement.report_number}.pdf"
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
