"""Read-only compliance records for WhatsApp consent and deliveries."""

from django.contrib import admin

from .whatsapp import WhatsAppDelivery, WhatsAppPreference


@admin.register(WhatsAppPreference)
class WhatsAppPreferenceAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "tutor",
        "number",
        "opted_in",
        "consent_recorded_at",
        "consent_source",
    )
    list_filter = ("opted_in",)
    search_fields = ("number", "student__email", "tutor__email")
    readonly_fields = (
        "student",
        "tutor",
        "number",
        "opted_in",
        "consent_recorded_at",
        "consent_source",
        "created_at",
    )

    def has_add_permission(self, request):
        # Admin cannot manufacture affirmative consent records.
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WhatsAppDelivery)
class WhatsAppDeliveryAdmin(admin.ModelAdmin):
    list_display = (
        "booking",
        "kind",
        "slot_start",
        "status",
        "attempts",
        "receipt_status",
        "sent_at",
    )
    list_filter = ("kind", "status", "receipt_status")
    search_fields = ("booking__reference", "provider_id")
    readonly_fields = (
        "booking",
        "preference",
        "kind",
        "slot_start",
        "status",
        "attempts",
        "next_attempt_at",
        "last_attempt_at",
        "sent_at",
        "provider_id",
        "receipt_status",
        "error_code",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
