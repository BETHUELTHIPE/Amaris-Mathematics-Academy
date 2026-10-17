"""Student-scoped staging invoices; no object path, signed URL or donor PII is disclosed."""
from __future__ import annotations

import io

from django.http import FileResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response

from content.models import LiveClassBooking, Payment
from content.payment_models import Invoice
from content.student_views import StudentAPIView
from content.services.staging_payment_receipts import (
    StagingReceiptUnavailable,
    course_receipt,
    live_class_receipt,
)


def _download(pdf: bytes, number: str):
    response = FileResponse(io.BytesIO(pdf), as_attachment=True, filename=f"{number}.pdf")
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


class StagingStudentOrdersView(StudentAPIView):
    @extend_schema(responses={200: list})
    def get(self, request):
        student = request.user.student
        records = []
        payments = (
            Payment.objects.filter(student=student)
            .select_related("course", "invoice")[:100]
        )
        for payment in payments:
            try:
                invoice = payment.invoice
            except Invoice.DoesNotExist:
                invoice = None
            verified = bool(
                invoice
                and payment.status == Payment.Status.PAID
                and payment.gateway_verified_at
            )
            records.append({
                "kind": "course",
                "reference": payment.reference,
                "title": payment.course.title,
                "amount": f"{payment.amount:.2f}",
                "currency": payment.currency,
                "status": payment.status,
                "invoice_number": invoice.invoice_number if verified else None,
                "invoice_ready": verified,
                "created_at": payment.created_at,
            })
        for booking in (
            LiveClassBooking.objects.filter(student=student)
            .select_related("slot", "slot__tutor")[:100]
        ):
            verified = bool(
                booking.invoice_number
                and booking.gateway_verified_at
                and booking.status == LiveClassBooking.Status.CONFIRMED
            )
            records.append({
                "kind": "live_class",
                "reference": booking.reference,
                "title": f"Live class: {booking.topic}",
                "amount": f"{booking.amount:.2f}",
                "currency": booking.currency,
                "status": booking.status,
                "invoice_number": booking.invoice_number if verified else None,
                "invoice_ready": verified,
                "created_at": booking.created_at,
            })
        return Response(records, headers={"Cache-Control": "private, no-store"})


class StagingCourseInvoiceView(StudentAPIView):
    @extend_schema(responses={200: bytes, 404: dict, 503: dict})
    def get(self, request, reference: str):
        invoice = (
            Invoice.objects.select_related("student", "payment", "course")
            .filter(
                payment__reference=reference,
                student=request.user.student,
                payment__status=Payment.Status.PAID,
                payment__gateway_verified_at__isnull=False,
            )
            .first()
        )
        if invoice is None:
            return Response({"detail": "Invoice not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            pdf = course_receipt(invoice)
        except StagingReceiptUnavailable:
            return Response(
                {"detail": "Private invoice storage is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return _download(pdf, invoice.invoice_number)


class StagingLiveClassInvoiceView(StudentAPIView):
    @extend_schema(responses={200: bytes, 404: dict, 503: dict})
    def get(self, request, reference: str):
        booking = (
            LiveClassBooking.objects.select_related("student", "slot", "slot__tutor")
            .filter(
                reference=reference,
                student=request.user.student,
                status=LiveClassBooking.Status.CONFIRMED,
                gateway_verified_at__isnull=False,
            )
            .first()
        )
        if booking is None or not booking.invoice_number:
            return Response({"detail": "Invoice not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            pdf = live_class_receipt(booking)
        except StagingReceiptUnavailable:
            return Response(
                {"detail": "Private invoice storage is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return _download(pdf, booking.invoice_number)
