from django.contrib import admin

from .subscription_models import CurriculumSubscription


@admin.register(CurriculumSubscription)
class CurriculumSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("reference", "student", "curriculum", "months", "amount", "status", "gateway_mode", "ends_at")
    list_filter = ("status", "curriculum", "months", "gateway_mode")
    search_fields = ("reference", "student__email")

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
