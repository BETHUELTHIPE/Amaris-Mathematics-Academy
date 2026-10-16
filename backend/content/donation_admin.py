from django.contrib import admin

from .donation_models import DonationContribution


@admin.register(DonationContribution)
class DonationContributionAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "donor_name",
        "amount",
        "purpose",
        "status",
        "created_at",
        "paid_at",
        "receipt_sent_at",
    )
    list_filter = ("status", "purpose", "created_at")
    search_fields = ("reference", "donor_name", "donor_email", "provider_reference")
    readonly_fields = (
        "id",
        "reference",
        "donor_name",
        "donor_email",
        "amount",
        "purpose",
        "currency",
        "status",
        "provider_reference",
        "gateway_verified_at",
        "paid_at",
        "receipt_sent_at",
        "receipt_error",
        "last_callback_status",
        "created_at",
        "updated_at",
    )
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def has_delete_permission(self, request, obj=None):
        return False
