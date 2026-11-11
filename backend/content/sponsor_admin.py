from django.contrib import admin

from .sponsor_models import SponsorAccount, SponsorAllocation, SponsorContribution


@admin.register(SponsorAccount)
class SponsorAccountAdmin(admin.ModelAdmin):
    list_display = ("name", "organisation", "is_active", "annual_target")
    list_filter = ("is_active",)
    search_fields = ("name", "organisation", "supabase_user_id")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(SponsorContribution)
class SponsorContributionAdmin(admin.ModelAdmin):
    list_display = ("reference", "sponsor", "amount", "provider", "payment_mode", "status", "received_at")
    list_filter = ("status", "provider", "payment_mode", "received_at")
    search_fields = ("reference", "sponsor__name", "sponsor__organisation")
    autocomplete_fields = ("sponsor",)
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "provider",
        "payment_mode",
        "payment_idempotency_key",
        "payment_email",
        "provider_reference",
        "gateway_verified_at",
        "checkout_url",
        "initialization_started_at",
        "last_error_code",
    )

    def has_delete_permission(self, request, obj=None):
        # Online references and receipt history must survive callback retries.
        return bool(
            obj is not None
            and obj.provider == "manual"
            and obj.status == "pledged"
            and super().has_delete_permission(request, obj)
        )

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if obj is not None and obj.provider != "manual":
            return (*fields, "reference", "sponsor", "amount", "status", "received_at")
        return fields


@admin.register(SponsorAllocation)
class SponsorAllocationAdmin(admin.ModelAdmin):
    list_display = ("learner_label", "sponsor", "programme", "amount", "status", "share_progress")
    list_filter = ("status", "programme", "share_progress")
    search_fields = ("learner_label", "sponsor__name", "sponsor__organisation")
    autocomplete_fields = ("sponsor", "student")
    raw_id_fields = ("enrollment",)
    readonly_fields = ("id", "created_at", "updated_at")
