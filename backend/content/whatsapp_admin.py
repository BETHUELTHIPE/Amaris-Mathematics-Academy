from django.contrib import admin
from .whatsapp import WhatsAppPreference, WhatsAppDelivery


@admin.register(WhatsAppPreference)
class WhatsAppPreferenceAdmin(admin.ModelAdmin):
    list_display = ("number", "student", "tutor", "opted_in", "consent_recorded_at")
    list_filter = ("opted_in",)
    search_fields = ("number", "student__email", "tutor__email")
    def save_model(self, request, obj, form, change):
        # Admin cannot assume consent simply because a number was entered.
        if obj.opted_in and not obj.consent_recorded_at:
            from django.core.exceptions import ValidationError
            raise ValidationError("Consent timestamp must be provided.")
        obj.full_clean()
        super().save_model(request, obj, form, change)


@admin.register(WhatsAppDelivery)
class WhatsAppDeliveryAdmin(admin.ModelAdmin):
    list_display = ("booking", "preference", "kind", "slot_start", "status", "sent_at")
    list_filter = ("kind", "status")
    readonly_fields = ("booking", "preference", "kind", "slot_start", "status", "sent_at", "provider_id", "error_code", "created_at")
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
