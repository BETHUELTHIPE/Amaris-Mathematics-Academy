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
    list_display = ("reference", "sponsor", "amount", "status", "received_at")
    list_filter = ("status", "received_at")
    search_fields = ("reference", "sponsor__name", "sponsor__organisation")
    autocomplete_fields = ("sponsor",)
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(SponsorAllocation)
class SponsorAllocationAdmin(admin.ModelAdmin):
    list_display = ("learner_label", "sponsor", "programme", "amount", "status", "share_progress")
    list_filter = ("status", "programme", "share_progress")
    search_fields = ("learner_label", "sponsor__name", "sponsor__organisation")
    autocomplete_fields = ("sponsor", "student")
    raw_id_fields = ("enrollment",)
    readonly_fields = ("id", "created_at", "updated_at")
