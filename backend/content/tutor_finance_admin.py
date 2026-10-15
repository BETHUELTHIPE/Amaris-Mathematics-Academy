"""Superuser-only financial controls. Raw account numbers are write-only and encrypted."""
import re
from cryptography.fernet import Fernet, InvalidToken
from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.utils import timezone

from .tutor_finance_models import (
    TutorContract, TutorCourseAssignment, TutorEarning, TutorPaymentProfile, TutorPayout, TutorVideoRequest,
)
from .services.tutor_finance import record_video_delivery


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
    fields = ("tutor", "account_holder", "bank_name", "branch_code", "account_number",
              "masked_account", "is_active", "recipient_verified_at", "created_at", "updated_at")

    @admin.display(description="Account")
    def masked_account(self, obj):
        return f"•••• {obj.account_last_four}" if obj.account_last_four else "Not configured"

    def save_model(self, request, obj, form, change):
        if not getattr(settings, "TUTOR_BANK_FERNET_KEY", "") and form.cleaned_data.get("account_number"):
            raise ValidationError("Configure the account encryption key first.")
        super().save_model(request, obj, form, change)


@admin.register(TutorContract)
class TutorContractAdmin(FinanceSuperuserAdmin):
    list_display = ("tutor", "service", "tutor_percent", "academy_percent", "contract_reference", "effective_from", "is_active")
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
    list_display = ("tutor", "service", "service_label", "gross", "tutor_percent", "tutor_amount", "academy_amount", "state")
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


@admin.register(TutorVideoRequest)
class TutorVideoRequestAdmin(FinanceSuperuserAdmin):
    list_display = ("reference", "tutor", "topic", "price", "status", "gateway_verified_at", "delivered_at")
    list_filter = ("status",)
    search_fields = ("reference", "topic", "tutor__username")
    readonly_fields = [field.name for field in TutorVideoRequest._meta.fields]
    actions = ("mark_delivered",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.action(description="Confirm topical video delivered after verifying private asset")
    def mark_delivered(self, request, queryset):
        count = 0
        for item in queryset:
            if item.status == TutorVideoRequest.Status.PAID and item.gateway_verified_at:
                record_video_delivery(item)
                count += 1
        self.message_user(request, f"Marked {count} verified paid requests as delivered.", messages.SUCCESS)
