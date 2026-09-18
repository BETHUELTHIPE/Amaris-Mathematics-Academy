from __future__ import annotations

import ipaddress
from datetime import timedelta

from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import SupabaseBearerAuthentication, SupabasePrincipal
from .models import Course, Enrollment, Lesson, Payment, StudentRecord
from .payment_models import PaymentWebhookEvent
from .services.payfast_security import (
    PayFastConfig,
    PayFastConfigurationError,
    PayFastVerifier,
    build_payfast_checkout_fields,
)
from .services.payments import (
    PAYMENT_WEBHOOK_MAX_AGE_HOURS,
    PaymentSecurityError,
    create_checkout,
    process_payfast_notification,
)


def _private(response: Response) -> Response:
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["Vary"] = "Authorization"
    return response


def _clean_text(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _student_for(principal: SupabasePrincipal) -> StudentRecord:
    metadata = principal.metadata
    first_name = _clean_text(metadata.get("first_name"), 80) or "Student"
    last_name = _clean_text(metadata.get("last_name"), 80)
    mobile = _clean_text(metadata.get("mobile") or metadata.get("phone"), 30)
    institution = _clean_text(metadata.get("institution"), 160)
    academic_level = _clean_text(metadata.get("academic_level"), 100)

    try:
        student, created = StudentRecord.objects.get_or_create(
            supabase_user_id=principal.id,
            defaults={
                "email": principal.email,
                "first_name": first_name,
                "last_name": last_name,
                "mobile": mobile,
                "institution": institution,
                "academic_level": academic_level,
                "is_active": True,
            },
        )
        if not created:
            student.email = principal.email
            student.first_name = first_name
            student.last_name = last_name
            student.mobile = mobile
            student.institution = institution
            student.academic_level = academic_level
            student.save(
                update_fields=[
                    "email",
                    "first_name",
                    "last_name",
                    "mobile",
                    "institution",
                    "academic_level",
                    "updated_at",
                ]
            )
    except IntegrityError as exc:
        raise PaymentSecurityError("Student identity conflicts with an existing account.") from exc
    return student


def _require_verified(principal: SupabasePrincipal) -> None:
    if not principal.email_verified:
        raise PaymentSecurityError("Verify your email before using paid learning services.")


def _course(slug: str) -> Course:
    now = timezone.now()
    course = (
        Course.objects.filter(
            slug=slug,
            status=Course.Status.PUBLISHED,
            is_published=True,
        )
        .filter(Q(publish_at__isnull=True) | Q(publish_at__lte=now))
        .first()
    )
    if course is None:
        raise Course.DoesNotExist
    return course


def _enrollment(student: StudentRecord, course_slug: str) -> Enrollment:
    enrollment = (
        Enrollment.objects.select_related("course", "last_lesson")
        .filter(
            student=student,
            course__slug=course_slug,
            status__in=[Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED],
        )
        .first()
    )
    if enrollment is None:
        raise Enrollment.DoesNotExist
    return enrollment


def _payment_state(payment: Payment) -> str:
    if payment.status != Payment.Status.PENDING:
        return payment.status
    if payment.created_at < timezone.now() - timedelta(hours=PAYMENT_WEBHOOK_MAX_AGE_HOURS):
        return "expired"
    latest_event = payment.webhook_events.order_by("-created_at").first()
    if latest_event and latest_event.state == PaymentWebhookEvent.State.RETRYABLE:
        return "processing"
    return "pending"


def _payfast_config() -> PayFastConfig:
    return PayFastConfig.from_environment()


def _checkout_payload(payment: Payment) -> dict:
    config = _payfast_config()
    base_fields = {
        "m_payment_id": payment.reference,
        "amount": f"{payment.amount:.2f}",
        "item_name": payment.course.title,
        "custom_str1": str(payment.student.supabase_user_id),
        "custom_str2": payment.course.slug,
    }
    fields = build_payfast_checkout_fields(
        base_fields,
        config=config,
        customer_fields={
            "name_first": payment.student.first_name,
            "name_last": payment.student.last_name,
            "email_address": payment.student.email,
            "cell_number": payment.student.mobile,
        },
    )
    return {
        "reference": payment.reference,
        "gateway_url": config.process_url,
        "fields": fields,
        "state": _payment_state(payment),
    }


def _callback_source_ip(request) -> str:
    values = []
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        values.extend(part.strip() for part in forwarded.split(",") if part.strip())
    remote = request.META.get("REMOTE_ADDR", "")
    if remote:
        values.append(remote.strip())

    for value in reversed(values):
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            continue
        if not (address.is_private or address.is_loopback or address.is_reserved or address.is_unspecified):
            return str(address)
    return values[-1] if values else ""


class StudentAPIView(APIView):
    authentication_classes = (SupabaseBearerAuthentication,)
    permission_classes = (IsAuthenticated,)

    @property
    def principal(self) -> SupabasePrincipal:
        return self.request.user


class CheckoutStartView(StudentAPIView):
    def post(self, request):
        try:
            _require_verified(self.principal)
            slug = _clean_text(request.data.get("course_slug"), 200)
            idempotency_key = _clean_text(request.data.get("idempotency_key"), 64)
            course = _course(slug)
            student = _student_for(self.principal)
            checkout = create_checkout(student=student, course=course, idempotency_key=idempotency_key)
            payment = Payment.objects.select_related("student", "course").get(reference=checkout.payment_reference)
            response = Response(_checkout_payload(payment), status=status.HTTP_201_CREATED)
        except (Course.DoesNotExist, Payment.DoesNotExist):
            response = Response({"detail": "Course or checkout was not found."}, status=status.HTTP_404_NOT_FOUND)
        except (PaymentSecurityError, PayFastConfigurationError) as exc:
            code = (
                status.HTTP_503_SERVICE_UNAVAILABLE
                if isinstance(exc, PayFastConfigurationError)
                else status.HTTP_400_BAD_REQUEST
            )
            response = Response({"detail": str(exc)}, status=code)
        return _private(response)


class CheckoutDetailView(StudentAPIView):
    def get(self, request, reference: str):
        student = _student_for(self.principal)
        payment = (
            Payment.objects.select_related("student", "course").filter(reference=reference, student=student).first()
        )
        if payment is None:
            return _private(Response({"detail": "Checkout was not found."}, status=status.HTTP_404_NOT_FOUND))
        state = _payment_state(payment)
        if state in {"paid", "refunded", "expired"}:
            return _private(
                Response(
                    {"reference": payment.reference, "state": state},
                    status=status.HTTP_409_CONFLICT,
                )
            )
        try:
            response = Response(_checkout_payload(payment))
        except PayFastConfigurationError as exc:
            response = Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return _private(response)


class PaymentStatusView(StudentAPIView):
    def get(self, request, reference: str):
        student = _student_for(self.principal)
        payment = (
            Payment.objects.select_related("course", "enrollment").filter(reference=reference, student=student).first()
        )
        if payment is None:
            return _private(Response({"detail": "Payment was not found."}, status=status.HTTP_404_NOT_FOUND))

        invoice_number = None
        if hasattr(payment, "invoice"):
            invoice_number = payment.invoice.invoice_number
        response = Response(
            {
                "reference": payment.reference,
                "state": _payment_state(payment),
                "course_slug": payment.course.slug,
                "course_title": payment.course.title,
                "amount": f"{payment.amount:.2f}",
                "currency": payment.currency,
                "gateway_verified": bool(payment.gateway_verified_at),
                "enrollment_active": bool(
                    payment.enrollment_id
                    and payment.enrollment
                    and payment.enrollment.status in {Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED}
                ),
                "invoice_number": invoice_number,
            }
        )
        return _private(response)


class StudentDashboardView(StudentAPIView):
    def get(self, request):
        _require_verified(self.principal)
        student = _student_for(self.principal)
        enrollments = (
            Enrollment.objects.select_related("course", "last_lesson")
            .filter(student=student, status__in=[Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED])
            .order_by("-enrolled_at")
        )
        items = []
        for enrollment in enrollments:
            last_lesson = enrollment.last_lesson
            if last_lesson is None:
                last_lesson = (
                    Lesson.objects.filter(
                        module__course=enrollment.course,
                        is_published=True,
                    )
                    .filter(Q(publish_at__isnull=True) | Q(publish_at__lte=timezone.now()))
                    .order_by("module__order", "order", "id")
                    .first()
                )
            items.append(
                {
                    "course_slug": enrollment.course.slug,
                    "course_title": enrollment.course.title,
                    "progress_percent": enrollment.progress_percent,
                    "last_position_seconds": enrollment.last_position_seconds,
                    "continue_lesson": (
                        {
                            "slug": last_lesson.slug,
                            "title": last_lesson.title,
                        }
                        if last_lesson
                        else None
                    ),
                }
            )
        return _private(Response({"enrollments": items}))


class EnrollmentProgressView(StudentAPIView):
    def get(self, request, course_slug: str):
        student = _student_for(self.principal)
        try:
            enrollment = _enrollment(student, course_slug)
        except Enrollment.DoesNotExist:
            return _private(Response({"detail": "Active enrollment was not found."}, status=status.HTTP_404_NOT_FOUND))
        return _private(Response(self._serialize(enrollment)))

    def put(self, request, course_slug: str):
        student = _student_for(self.principal)
        try:
            enrollment = _enrollment(student, course_slug)
        except Enrollment.DoesNotExist:
            return _private(Response({"detail": "Active enrollment was not found."}, status=status.HTTP_404_NOT_FOUND))

        lesson_slug = _clean_text(request.data.get("lesson_slug"), 200)
        lesson = (
            Lesson.objects.filter(
                module__course=enrollment.course,
                slug=lesson_slug,
                is_published=True,
            )
            .filter(Q(publish_at__isnull=True) | Q(publish_at__lte=timezone.now()))
            .first()
        )
        if lesson is None:
            return _private(Response({"detail": "Lesson was not found."}, status=status.HTTP_404_NOT_FOUND))

        try:
            position = max(0, int(request.data.get("position_seconds", 0)))
        except (TypeError, ValueError):
            return _private(Response({"detail": "Invalid lesson position."}, status=status.HTTP_400_BAD_REQUEST))
        if lesson.duration_minutes:
            position = min(position, lesson.duration_minutes * 60)

        live_lessons = list(
            Lesson.objects.filter(module__course=enrollment.course, is_published=True)
            .filter(Q(publish_at__isnull=True) | Q(publish_at__lte=timezone.now()))
            .order_by("module__order", "order", "id")
            .values_list("id", flat=True)
        )
        completed = request.data.get("completed") is True
        if live_lessons and lesson.id in live_lessons:
            ordinal = live_lessons.index(lesson.id) + (1 if completed else 0)
            calculated = min(100, round((ordinal / len(live_lessons)) * 100))
            enrollment.progress_percent = max(enrollment.progress_percent, calculated)

        enrollment.last_lesson = lesson
        enrollment.last_position_seconds = position
        enrollment.save(
            update_fields=[
                "last_lesson",
                "last_position_seconds",
                "progress_percent",
                "updated_at",
            ]
        )
        return _private(Response(self._serialize(enrollment)))

    @staticmethod
    def _serialize(enrollment: Enrollment) -> dict:
        lesson = enrollment.last_lesson
        return {
            "course_slug": enrollment.course.slug,
            "progress_percent": enrollment.progress_percent,
            "last_position_seconds": enrollment.last_position_seconds,
            "last_lesson": ({"slug": lesson.slug, "title": lesson.title} if lesson else None),
        }


class ProtectedLessonView(StudentAPIView):
    def get(self, request, course_slug: str, lesson_slug: str):
        student = _student_for(self.principal)
        try:
            enrollment = _enrollment(student, course_slug)
        except Enrollment.DoesNotExist:
            return _private(Response({"detail": "Active enrollment was not found."}, status=status.HTTP_404_NOT_FOUND))

        lesson = (
            Lesson.objects.select_related("module", "video")
            .filter(
                module__course=enrollment.course,
                slug=lesson_slug,
                is_published=True,
            )
            .filter(Q(publish_at__isnull=True) | Q(publish_at__lte=timezone.now()))
            .first()
        )
        if lesson is None:
            return _private(Response({"detail": "Lesson was not found."}, status=status.HTTP_404_NOT_FOUND))

        video_url = None
        if lesson.video_id and lesson.video:
            video_url = lesson.video.youtube_url or (lesson.video.source_file.url if lesson.video.source_file else None)
        return _private(
            Response(
                {
                    "course_slug": enrollment.course.slug,
                    "course_title": enrollment.course.title,
                    "lesson_slug": lesson.slug,
                    "title": lesson.title,
                    "summary": lesson.summary,
                    "lesson_body": lesson.lesson_body,
                    "duration_minutes": lesson.duration_minutes,
                    "video_url": video_url,
                    "position_seconds": (
                        enrollment.last_position_seconds if enrollment.last_lesson_id == lesson.id else 0
                    ),
                }
            )
        )


class PayFastITNView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def post(self, request):
        payload = {str(key): str(value) for key, value in request.data.items()}
        try:
            config = _payfast_config()
            verifier = PayFastVerifier(
                config=config,
                source_ip=_callback_source_ip(request),
            )
            result = process_payfast_notification(payload, gateway=verifier)
        except PayFastConfigurationError:
            return Response("UNAVAILABLE", status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except PaymentSecurityError:
            return Response("REJECTED", status=status.HTTP_400_BAD_REQUEST)

        if result.retryable:
            return Response("RETRY", status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response("OK", status=status.HTTP_200_OK)
