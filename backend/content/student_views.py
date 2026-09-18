from __future__ import annotations

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import SupabaseStudentAuthentication
from .models import Course, Enrollment, Lesson, Payment
from .services.payments import PaymentSecurityError, create_checkout


class CheckoutRequestSerializer(serializers.Serializer):
    course_slug = serializers.SlugField(max_length=200)
    idempotency_key = serializers.RegexField(r"^[A-Za-z0-9_-]{8,64}$")


class ProgressRequestSerializer(serializers.Serializer):
    course_slug = serializers.SlugField(max_length=200)
    lesson_slug = serializers.SlugField(max_length=200)
    position_seconds = serializers.IntegerField(min_value=0, max_value=24 * 60 * 60)
    progress_percent = serializers.IntegerField(min_value=0, max_value=100, required=False)


class StudentAPIView(APIView):
    authentication_classes = (SupabaseStudentAuthentication,)
    permission_classes = (IsAuthenticated,)

    @property
    def student(self):
        return self.request.user.student


class StudentCoursesView(StudentAPIView):
    def get(self, request):
        enrollments = (
            Enrollment.objects.filter(
                student=request.user.student,
                status__in=[Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED],
            )
            .select_related("course", "last_lesson", "last_lesson__module")
            .order_by("-enrolled_at")
        )
        return Response(
            [
                {
                    "course": {
                        "slug": enrollment.course.slug,
                        "title": enrollment.course.title,
                    },
                    "resume": _resume_payload(enrollment),
                }
                for enrollment in enrollments
            ]
        )


class StudentLessonView(StudentAPIView):
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
                            "youtube_video_id": video.youtube_video_id if video.provider == video.Provider.YOUTUBE else "",
                            "duration_seconds": video.duration_seconds,
                        }
                        if video
                        else None
                    ),
                },
                "resume": _resume_payload(enrollment),
            }
        )


class CheckoutView(StudentAPIView):
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
