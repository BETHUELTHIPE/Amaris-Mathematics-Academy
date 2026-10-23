"""Private, superuser-only Django Admin download of archived class invoices."""

from botocore.exceptions import BotoCoreError, ClientError
from django.contrib import admin
from django.core.files.storage import storages
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html

from .models import LiveClassBooking
from .services.invoices import student_invoice_key


class LiveClassInvoiceAdminMixin:
    def get_urls(self):
        invoice_urls = [
            path(
                "<uuid:object_id>/invoice/",
                self.admin_site.admin_view(self.download_invoice_pdf),
                name="content_liveclassbooking_invoice",
            ),
        ]
        return invoice_urls + super().get_urls()

    @admin.display(description="Archived invoice PDF")
    def invoice_pdf(self, obj):
        if (
            not obj.invoice_number
            or not obj.confirmation_sent_at
            or obj.status not in (LiveClassBooking.Status.CONFIRMED, LiveClassBooking.Status.COMPLETED)
        ):
            return "Not available until payment is confirmed"
        url = reverse("admin:content_liveclassbooking_invoice", args=[obj.pk])
        return format_html('<a href="{}">Download invoice PDF</a>', url)

    def download_invoice_pdf(self, request, object_id):
        if not request.user.is_active or not request.user.is_superuser:
            raise Http404("Invoice not found.")
        booking = get_object_or_404(
            LiveClassBooking,
            pk=object_id,
            status__in=(LiveClassBooking.Status.CONFIRMED, LiveClassBooking.Status.COMPLETED),
            confirmation_sent_at__isnull=False,
        )
        if not booking.invoice_number:
            raise Http404("Invoice not found.")
        key = student_invoice_key(booking.student.supabase_user_id, booking.invoice_number)
        try:
            document = storages["student_private"].open(key, "rb")
        except (OSError, ValueError, BotoCoreError, ClientError):
            return HttpResponse("Invoice storage temporarily unavailable.", status=503)
        response = FileResponse(document, as_attachment=True, filename=f"{booking.invoice_number}.pdf")
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
