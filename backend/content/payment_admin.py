from django.contrib import admin

from .payment_models import Invoice, NotificationOutbox, PaymentWebhookEvent, ServiceTicket


class ImmutablePaymentArtifactAdmin(admin.ModelAdmin):
    list_per_page = 30

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentWebhookEvent)
class PaymentWebhookEventAdmin(ImmutablePaymentArtifactAdmin):
    list_display = (
        "provider_reference",
        "payment_status",
        "local_reference",
        "state",
        "attempts",
        "verified_at",
        "processed_at",
    )
    list_filter = ("provider", "payment_status", "state", "created_at")
    search_fields = ("provider_reference", "local_reference", "payment__reference")
    readonly_fields = (
        "provider",
        "provider_reference",
        "payment_status",
        "local_reference",
        "payment",
        "payload_hash",
        "state",
        "attempts",
        "last_error_code",
        "verified_at",
        "processed_at",
        "created_at",
        "updated_at",
    )


@admin.register(Invoice)
class InvoiceAdmin(ImmutablePaymentArtifactAdmin):
    list_display = ("invoice_number", "student", "course", "amount", "currency", "issued_at")
    search_fields = ("invoice_number", "payment__reference", "student__email", "course__title")
    readonly_fields = (
        "payment",
        "invoice_number",
        "student",
        "course",
        "amount",
        "currency",
        "issued_at",
        "created_at",
        "updated_at",
    )


@admin.register(ServiceTicket)
class ServiceTicketAdmin(ImmutablePaymentArtifactAdmin):
    list_display = ("ticket_number", "payment", "enrollment", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("ticket_number", "payment__reference", "enrollment__student__email")
    readonly_fields = ("payment", "enrollment", "ticket_number", "status", "created_at", "updated_at")


@admin.register(NotificationOutbox)
class NotificationOutboxAdmin(ImmutablePaymentArtifactAdmin):
    list_display = ("event_type", "payment", "destination", "status", "created_at")
    list_filter = ("status", "event_type", "created_at")
    search_fields = ("payment__reference", "destination")
    readonly_fields = (
        "payment",
        "event_type",
        "destination",
        "status",
        "payload",
        "created_at",
        "updated_at",
    )
