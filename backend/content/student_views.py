from __future__ import annotations

import os

from botocore.exceptions import BotoCoreError, ClientError
from django.core.files.storage import storages
from django.db import transaction
from django.db.models import OuterRef, Q, Subquery
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import SupabaseStudentAuthentication
from .models import (
    Course,
    CourseCategory,
    CourseModule,
    Enrollment,
    Lesson,
    LiveClassBooking,
    Payment,
    VideoRequest,
)
from .payment_models import Invoice, NotificationOutbox
from .serializers import (
    AcceptancePaymentCompleteResponseSerializer,
    AcceptanceSeedResponseSerializer,
    CheckoutResponseSerializer,
    PaymentConflictResponseSerializer,
    PaymentStatusResponseSerializer,
    ResumeSerializer,
    StudentCourseEnrollmentSerializer,
    StudentLessonResponseSerializer,
)
from .services.invoices import InvoiceArchiveError, archive_invoice_pdf, invoice_storage_path
from .services.payments import PaymentSecurityError, create_checkout, process_payfast_notification


class CheckoutRequestSerializer(serializers.Serializer):
    course_slug = serializers.SlugField(max_length=200)
    idempotency_key = serializers.RegexField(r"^[A-Za-z0-9_-]{8,64}$")


class ProgressRequestSerializer(serializers.Serializer):
    course_slug = serializers.SlugField(max_length=200)
    lesson_slug = serializers.SlugField(max_length=200)
    position_seconds = serializers.IntegerField(min_value=0, max_value=24 * 60 * 60)
    progress_percent = serializers.IntegerField(min_value=0, max_value=100, required=False)


class StudentOrderSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=("course", "live_class", "video_request"))
    reference = serializers.CharField()
    title = serializers.CharField()
    detail = serializers.CharField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField()
    status = serializers.CharField()
    status_label = serializers.CharField()
    created_at = serializers.DateTimeField()
    paid_at = serializers.DateTimeField(allow_null=True)
    invoice_number = serializers.CharField(allow_blank=True, allow_null=True)
    invoice_ready = serializers.BooleanField()
    href = serializers.CharField()


class StudentNotificationSerializer(serializers.Serializer):
    id = serializers.CharField()
    category = serializers.ChoiceField(choices=("payment", "live_class", "video_request"))
    title = serializers.CharField()
    message = serializers.CharField()
    delivery_status = serializers.CharField()
    occurred_at = serializers.DateTimeField()
    href = serializers.CharField()


class StudentAPIView(APIView):
    authentication_classes = (SupabaseStudentAuthentication,)
    permission_classes = (IsAuthenticated,)

    @property
    def student(self):
        return self.request.user.student

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class StudentCoursesView(StudentAPIView):
    @extend_schema(responses=StudentCourseEnrollmentSerializer(many=True))
    def get(self, request):
        enrollments = (
            Enrollment.objects.filter(
                student=request.user.student,
                status__in=[Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED],
            )
            .select_related("course", "last_lesson", "last_lesson__module")
            .annotate(
                first_lesson_slug=Subquery(
                    Lesson.objects.filter(
                        Q(publish_at__isnull=True) | Q(publish_at__lte=timezone.now()),
                        module__course_id=OuterRef("course_id"),
                        module__is_published=True,
                        is_published=True,
                    )
                    .order_by("module__order", "order", "id")
                    .values("slug")[:1]
                )
            )
            .order_by("-enrolled_at")
        )
        return Response(
            [
                {
                    "course": {
                        "slug": enrollment.course.slug,
                        "title": enrollment.course.title,
                        "first_lesson_slug": enrollment.first_lesson_slug or "",
                    },
                    "resume": _resume_payload(enrollment),
                }
                for enrollment in enrollments
            ]
        )


class StudentOrdersView(StudentAPIView):
    @extend_schema(responses=StudentOrderSerializer(many=True))
    def get(self, request):
        student = request.user.student
        orders = []

        payments = Payment.objects.filter(student=student).select_related("course", "invoice")[:100]
        for payment in payments:
            try:
                invoice = payment.invoice
            except Invoice.DoesNotExist:
                invoice = None
            orders.append(
                {
                    "kind": "course",
                    "reference": payment.reference,
                    "title": payment.course.title,
                    "detail": "Course enrolment",
                    "amount": payment.amount,
                    "currency": payment.currency,
                    "status": payment.status,
                    "status_label": payment.get_status_display(),
                    "created_at": payment.created_at,
                    "paid_at": payment.paid_at,
                    "invoice_number": invoice.invoice_number if invoice else None,
                    "invoice_ready": bool(
                        invoice and payment.status == Payment.Status.PAID and payment.gateway_verified_at
                    ),
                    "href": f"/courses/{payment.course.slug}",
                }
            )

        bookings = LiveClassBooking.objects.filter(student=student).select_related("slot", "slot__tutor")[:100]
        for booking in bookings:
            orders.append(
                {
                    "kind": "live_class",
                    "reference": booking.reference,
                    "title": booking.topic,
                    "detail": f"Online live class with {booking.slot.tutor_display_name}",
                    "amount": booking.amount,
                    "currency": booking.currency,
                    "status": booking.status,
                    "status_label": booking.get_status_display(),
                    "created_at": booking.created_at,
                    "paid_at": booking.paid_at,
                    "invoice_number": booking.invoice_number,
                    "invoice_ready": bool(booking.invoice_number and booking.confirmation_sent_at),
                    "href": f"/book-online-live-class/confirmation?reference={booking.reference}",
                }
            )

        video_requests = VideoRequest.objects.filter(student=student)[:100]
        for item in video_requests:
            orders.append(
                {
                    "kind": "video_request",
                    "reference": item.reference,
                    "title": item.topic,
                    "detail": item.get_request_type_display(),
                    "amount": item.amount,
                    "currency": item.currency,
                    "status": item.status,
                    "status_label": item.get_status_display(),
                    "created_at": item.created_at,
                    "paid_at": item.paid_at,
                    "invoice_number": item.invoice_number,
                    "invoice_ready": bool(item.invoice_number and item.confirmation_sent_at),
                    "href": f"/request-a-video/confirmation?reference={item.reference}",
                }
            )

        orders.sort(key=lambda item: item["created_at"], reverse=True)
        return Response(orders[:100])


class StudentNotificationsView(StudentAPIView):
    @extend_schema(responses=StudentNotificationSerializer(many=True))
    def get(self, request):
        student = request.user.student
        notifications = []

        payment_notifications = (
            NotificationOutbox.objects.filter(payment__student=student)
            .select_related("payment", "payment__course")
            .order_by("-updated_at")[:100]
        )
        for item in payment_notifications:
            notifications.append(
                {
                    "id": f"payment-{item.pk}",
                    "category": "payment",
                    "title": "Payment confirmation",
                    "message": f"{item.payment.course.title}: {item.payment.get_status_display()}.",
                    "delivery_status": item.get_status_display(),
                    "occurred_at": item.updated_at,
                    "href": "/dashboard/orders",
                }
            )

        for booking in LiveClassBooking.objects.filter(student=student).select_related("slot", "slot__tutor")[:100]:
            if booking.confirmation_sent_at:
                notifications.append(
                    {
                        "id": f"live-confirmed-{booking.pk}",
                        "category": "live_class",
                        "title": "Live class confirmed",
                        "message": f"{booking.topic} with {booking.slot.tutor_display_name} is confirmed.",
                        "delivery_status": "Sent",
                        "occurred_at": booking.confirmation_sent_at,
                        "href": f"/book-online-live-class/confirmation?reference={booking.reference}",
                    }
                )
            if booking.reminder_sent_at:
                notifications.append(
                    {
                        "id": f"live-reminder-{booking.pk}",
                        "category": "live_class",
                        "title": "Live class reminder",
                        "message": f"Your class on {booking.topic} starts soon.",
                        "delivery_status": "Sent",
                        "occurred_at": booking.reminder_sent_at,
                        "href": f"/book-online-live-class/confirmation?reference={booking.reference}",
                    }
                )

        video_events = (
            ("confirmation_sent_at", "Video request queued", "Your paid video request is in the tutor queue."),
            ("position_one_sent_at", "Your video request is next", "Your request has reached the front of the queue."),
            ("recording_sent_at", "Video recording started", "A tutor has started preparing your explanation."),
            (
                "ready_notification_sent_at",
                "Your requested video is ready",
                "Your private explanation is ready to watch.",
            ),
        )
        for item in VideoRequest.objects.filter(student=student)[:100]:
            for field, title, message in video_events:
                occurred_at = getattr(item, field)
                if occurred_at:
                    notifications.append(
                        {
                            "id": f"video-{field}-{item.pk}",
                            "category": "video_request",
                            "title": title,
                            "message": f"{item.topic}: {message}",
                            "delivery_status": "Sent",
                            "occurred_at": occurred_at,
                            "href": f"/request-a-video/confirmation?reference={item.reference}",
                        }
                    )

        notifications.sort(key=lambda item: item["occurred_at"], reverse=True)
        return Response(notifications[:100])


class StudentCourseInvoiceDownloadView(StudentAPIView):
    @extend_schema(
        responses={
            (200, "application/pdf"): OpenApiTypes.BINARY,
            404: OpenApiResponse(description="Invoice not found for this student."),
            503: OpenApiResponse(description="Invoice storage is temporarily unavailable."),
        }
    )
    def get(self, request, reference: str):
        invoice = (
            Invoice.objects.select_related("payment", "student", "course")
            .filter(
                payment__reference=reference,
                payment__student=request.user.student,
                student=request.user.student,
                payment__status=Payment.Status.PAID,
                payment__gateway_verified_at__isnull=False,
            )
            .first()
        )
        if invoice is None:
            return Response({"detail": "Invoice not found."}, status=status.HTTP_404_NOT_FOUND)

        storage = storages["student_private"]
        path = invoice_storage_path(invoice)
        try:
            if not storage.exists(path):
                archive_invoice_pdf(invoice, storage=storage)
            document = storage.open(path, "rb")
        except (OSError, ValueError, BotoCoreError, ClientError, InvoiceArchiveError):
            return Response(
                {"detail": "Invoice is temporarily unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        response = FileResponse(document, as_attachment=True, filename=f"{invoice.invoice_number}.pdf")
        response["Cache-Control"] = "private, no-store"
        return response


class StudentLessonView(StudentAPIView):
    @extend_schema(responses=StudentLessonResponseSerializer)
    def get(self, request, course_slug: str, lesson_slug: str):
        enrollment = get_object_or_404(
            Enrollment.objects.select_related("course"),
            student=request.user.student,
            course__slug=course_slug,
            status__in=[Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED],
        )
        lesson = get_object_or_404(
            Lesson.objects.select_related("module", "video"),
            Q(publish_at__isnull=True) | Q(publish_at__lte=timezone.now()),
            module__course=enrollment.course,
            module__is_published=True,
            slug=lesson_slug,
            is_published=True,
        )
        video = lesson.video
        return Response(
            {
                "course_slug": enrollment.course.slug,
                "course_title": enrollment.course.title,
                "lesson": {
                    "id": lesson.pk,
                    "slug": lesson.slug,
                    "title": lesson.title,
                    "summary": lesson.summary,
                    "lesson_body": lesson.lesson_body,
                    "duration_minutes": lesson.duration_minutes,
                    "module": lesson.module.title,
                    "video": (
                        {
                            "provider": video.provider,
                            "youtube_video_id": (
                                video.youtube_video_id if video.provider == video.Provider.YOUTUBE else ""
                            ),
                            "duration_seconds": video.duration_seconds,
                        }
                        if video
                        else None
                    ),
                },
                "resume": _resume_payload(enrollment),
            }
        )


class AcceptanceSeedView(StudentAPIView):
    """Create deterministic synthetic staging data for protected release checks only."""

    @extend_schema(request=None, responses={200: AcceptanceSeedResponseSerializer})
    def post(self, request):
        auth = request.auth if isinstance(request.auth, dict) else {}
        if auth.get("provider") != "github-actions-oidc":
            raise PermissionDenied("Synthetic acceptance seeding is restricted to GitHub Actions OIDC.")

        category, _ = CourseCategory.objects.get_or_create(
            slug="acceptance-testing",
            defaults={
                "name": "Acceptance Testing",
                "description": "Synthetic release-acceptance fixtures only.",
                "is_active": True,
            },
        )
        course, _ = Course.objects.update_or_create(
            slug="acceptance-capacity-mathematics",
            defaults={
                "category": category,
                "title": "Synthetic Acceptance Mathematics",
                "short_description": "Synthetic release-acceptance course.",
                "description": "No real student, payment, or academic data is used.",
                "curriculum": "Synthetic",
                "academic_level": "Acceptance",
                "price": "1.00",
                "status": Course.Status.PUBLISHED,
                "featured": False,
            },
        )
        module, _ = CourseModule.objects.update_or_create(
            course=course,
            order=1,
            defaults={
                "title": "Acceptance Algebra",
                "description": "Synthetic module.",
                "is_published": True,
            },
        )
        lesson, _ = Lesson.objects.update_or_create(
            module=module,
            order=1,
            defaults={
                "slug": "acceptance-algebra",
                "title": "Acceptance Algebra",
                "summary": "Synthetic lesson used only for release verification.",
                "lesson_body": "Synthetic lesson content. No real student data.",
                "duration_minutes": 20,
                "is_published": True,
                "is_free_preview": False,
            },
        )
        enrollment, _ = Enrollment.objects.update_or_create(
            student=request.user.student,
            course=course,
            defaults={"status": Enrollment.Status.ACTIVE},
        )
        if enrollment.status != Enrollment.Status.ACTIVE:
            enrollment.status = Enrollment.Status.ACTIVE
            enrollment.save(update_fields=["status", "updated_at"])

        Payment.objects.filter(
            student=request.user.student,
            course=course,
            status=Payment.Status.PENDING,
            reference__startswith="PF-acceptance-",
        ).delete()

        return Response(
            {
                "student": "synthetic",
                "course_slug": course.slug,
                "lesson_slug": lesson.slug,
                "enrollment_status": enrollment.status,
            }
        )


class _AcceptancePayFastGateway:
    def verify_notification(self, payload):
        del payload
        return True


class AcceptancePaymentCompleteView(StudentAPIView):
    """Complete one synthetic staging payment through the real fulfillment path."""

    @extend_schema(
        request=None,
        responses={200: AcceptancePaymentCompleteResponseSerializer, 409: PaymentConflictResponseSerializer},
    )
    def post(self, request, reference: str):
        auth = request.auth if isinstance(request.auth, dict) else {}
        if auth.get("provider") != "github-actions-oidc":
            raise PermissionDenied("Synthetic acceptance payment completion is restricted to GitHub Actions OIDC.")
        if os.getenv("PAYFAST_MODE", "sandbox").strip().lower() != "sandbox":
            raise PermissionDenied("Synthetic acceptance payment completion requires PayFast sandbox mode.")
        if not reference.startswith("PF-acceptance-"):
            raise PermissionDenied("Only synthetic acceptance payments can be completed.")

        payment = get_object_or_404(
            Payment.objects.select_related("student", "course"),
            reference=reference,
            student=request.user.student,
            course__slug="acceptance-capacity-mathematics",
        )
        payload = {
            "m_payment_id": payment.reference,
            "pf_payment_id": f"ACCEPTANCE-{payment.reference[-32:]}",
            "payment_status": "COMPLETE",
            "amount_gross": f"{payment.amount:.2f}",
            "custom_str1": str(payment.student.supabase_user_id),
            "custom_str2": payment.course.slug,
            "signature": "synthetic-acceptance-never-sent",
        }
        result = process_payfast_notification(payload, gateway=_AcceptancePayFastGateway())
        if not result.accepted:
            return Response(
                {"status": result.payment_status, "reason": result.reason},
                status=status.HTTP_409_CONFLICT,
            )

        payment.refresh_from_db()
        return Response(
            {
                "payment_reference": payment.reference,
                "status": payment.status,
                "enrollment_status": payment.enrollment.status if payment.enrollment_id else None,
            }
        )


class CheckoutView(StudentAPIView):
    @extend_schema(request=CheckoutRequestSerializer, responses={201: CheckoutResponseSerializer})
    def post(self, request):
        serializer = CheckoutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        course = get_object_or_404(
            Course,
            slug=values["course_slug"],
            status=Course.Status.PUBLISHED,
            is_published=True,
        )
        try:
            checkout = create_checkout(
                student=request.user.student,
                course=course,
                idempotency_key=values["idempotency_key"],
            )
        except PaymentSecurityError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc

        payment = Payment.objects.get(reference=checkout.payment_reference)
        return Response(
            {
                "payment_reference": checkout.payment_reference,
                "status": payment.status,
                "gateway_url": checkout.gateway_url,
                "fields": checkout.fields,
                "course": {"slug": course.slug, "title": course.title},
            },
            status=status.HTTP_201_CREATED,
        )


class PaymentStatusView(StudentAPIView):
    @extend_schema(responses=PaymentStatusResponseSerializer)
    def get(self, request, reference: str):
        payment = get_object_or_404(
            Payment.objects.select_related("enrollment", "course"),
            reference=reference,
            student=request.user.student,
        )
        return Response(
            {
                "payment_reference": payment.reference,
                "status": payment.status,
                "course_slug": payment.course.slug,
                "paid_at": payment.paid_at,
                "enrollment_status": payment.enrollment.status if payment.enrollment_id else None,
            }
        )


class ProgressView(StudentAPIView):
    @extend_schema(request=ProgressRequestSerializer, responses=ResumeSerializer)
    def patch(self, request):
        serializer = ProgressRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data

        with transaction.atomic():
            enrollment = get_object_or_404(
                Enrollment.objects.select_for_update().select_related("course"),
                student=request.user.student,
                course__slug=values["course_slug"],
                status__in=[Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED],
            )
            lesson = get_object_or_404(
                Lesson.objects.select_related("module"),
                Q(publish_at__isnull=True) | Q(publish_at__lte=timezone.now()),
                module__course=enrollment.course,
                slug=values["lesson_slug"],
                is_published=True,
                module__is_published=True,
            )
            enrollment.last_lesson = lesson
            enrollment.last_position_seconds = values["position_seconds"]
            enrollment.progress_updated_at = timezone.now()
            update_fields = ["last_lesson", "last_position_seconds", "progress_updated_at", "updated_at"]
            if "progress_percent" in values:
                enrollment.progress_percent = max(enrollment.progress_percent, values["progress_percent"])
                update_fields.append("progress_percent")
            enrollment.save(update_fields=update_fields)

        return Response(_resume_payload(enrollment))


class ResumeView(StudentAPIView):
    @extend_schema(responses=ResumeSerializer)
    def get(self, request, course_slug: str):
        enrollment = get_object_or_404(
            Enrollment.objects.select_related("course", "last_lesson", "last_lesson__module"),
            student=request.user.student,
            course__slug=course_slug,
            status__in=[Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED],
        )
        return Response(_resume_payload(enrollment))


def _resume_payload(enrollment: Enrollment) -> dict:
    lesson = enrollment.last_lesson
    return {
        "course_slug": enrollment.course.slug,
        "enrollment_status": enrollment.status,
        "progress_percent": enrollment.progress_percent,
        "last_position_seconds": enrollment.last_position_seconds,
        "last_lesson": (
            {
                "id": lesson.pk,
                "slug": lesson.slug,
                "title": lesson.title,
                "module": lesson.module.title,
            }
            if lesson
            else None
        ),
        "progress_updated_at": enrollment.progress_updated_at,
    }
