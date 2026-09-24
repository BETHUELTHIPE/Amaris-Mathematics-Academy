from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import SupabaseStudentAuthentication
from .models import CustomVideoRequest, TutorAvailabilitySlot
from .services.custom_videos import (
    SCHOOL_LEVELS,
    create_custom_video_checkout,
    create_custom_video_request,
    get_custom_video_settings,
)
from .services.payments import PaymentSecurityError


class CustomVideoOptionsResponseSerializer(serializers.Serializer):
    programmes = serializers.ListField()
    subjects = serializers.ListField()
    school_levels = serializers.ListField(child=serializers.CharField())
    caps_mathematics_topics = serializers.ListField(child=serializers.CharField())
    topic_source = serializers.CharField()
    topic_notice = serializers.CharField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    currency = serializers.CharField()
    checkout_enabled = serializers.BooleanField()
    max_files = serializers.IntegerField()
    max_file_size_mb = serializers.IntegerField()


class CustomVideoOptionsView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(responses={200: CustomVideoOptionsResponseSerializer})
    def get(self, request):
        settings_row = get_custom_video_settings()
        checkout_enabled = bool(settings_row and settings_row.checkout_enabled)
        return Response(
            {
                "programmes": [
                    {"value": value, "label": label}
                    for value, label in TutorAvailabilitySlot.Programme.choices
                ],
                "subjects": [
                    {"value": value, "label": label}
                    for value, label in TutorAvailabilitySlot.Subject.choices
                ],
                "school_levels": list(SCHOOL_LEVELS),
                # No LearningOutcome / AssessmentStandard model exists in the current
                # repository, so the API deliberately returns no invented CAPS topics.
                "caps_mathematics_topics": [],
                "topic_source": "free_text",
                "topic_notice": (
                    "Formal CAPS Learning Outcome / Assessment Standard topics are not "
                    "modelled in the current content database. Enter the topic from your "
                    "source material and upload the supporting document."
                ),
                "price": settings_row.flat_fee if checkout_enabled else None,
                "currency": settings_row.currency if settings_row else "ZAR",
                "checkout_enabled": checkout_enabled,
                "max_files": settings_row.max_files if settings_row else 5,
                "max_file_size_mb": settings_row.max_file_size_mb if settings_row else 20,
            }
        )


class CustomVideoRequestCreateSerializer(serializers.Serializer):
    programme = serializers.ChoiceField(choices=TutorAvailabilitySlot.Programme.choices)
    subject = serializers.ChoiceField(choices=TutorAvailabilitySlot.Subject.choices)
    level = serializers.CharField(min_length=2, max_length=80, trim_whitespace=True)
    topic = serializers.CharField(min_length=2, max_length=180, trim_whitespace=True)
    idempotency_key = serializers.RegexField(r"^[A-Za-z0-9_-]{8,64}$")


class CustomVideoRequestResponseSerializer(serializers.Serializer):
    request_reference = serializers.CharField()
    status = serializers.CharField()
    programme = serializers.CharField()
    subject = serializers.CharField()
    level = serializers.CharField()
    topic = serializers.CharField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    currency = serializers.CharField()
    invoice_number = serializers.CharField(allow_blank=True, allow_null=True)
    supporting_files = serializers.ListField()
    checkout_enabled = serializers.BooleanField()


class CustomVideoCheckoutResponseSerializer(serializers.Serializer):
    request_reference = serializers.CharField()
    status = serializers.CharField()
    gateway_url = serializers.URLField()
    fields = serializers.DictField(child=serializers.CharField())
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField()


class CustomVideoStudentAPIView(APIView):
    authentication_classes = (SupabaseStudentAuthentication,)
    permission_classes = (IsAuthenticated,)

    @property
    def student(self):
        return self.request.user.student


def _status_payload(video_request: CustomVideoRequest) -> dict:
    settings_row = get_custom_video_settings()
    return {
        "request_reference": video_request.reference,
        "status": video_request.status,
        "programme": video_request.get_programme_display(),
        "subject": video_request.get_subject_display(),
        "level": video_request.level,
        "topic": video_request.topic,
        "amount": video_request.amount,
        "currency": video_request.currency,
        "invoice_number": video_request.invoice_number,
        "supporting_files": [
            {
                "name": item.original_name,
                "content_type": item.content_type,
                "size_bytes": item.size_bytes,
            }
            for item in video_request.supporting_files.all()
        ],
        "checkout_enabled": bool(settings_row and settings_row.checkout_enabled),
    }


class CustomVideoRequestCreateView(CustomVideoStudentAPIView):
    parser_classes = (MultiPartParser, FormParser)

    @extend_schema(
        request=CustomVideoRequestCreateSerializer,
        responses={201: CustomVideoRequestResponseSerializer},
    )
    def post(self, request):
        serializer = CustomVideoRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        try:
            video_request = create_custom_video_request(
                student=request.user.student,
                programme=values["programme"],
                subject=values["subject"],
                level=values["level"],
                topic=values["topic"],
                idempotency_key=values["idempotency_key"],
                files=request.FILES.getlist("files"),
            )
        except PaymentSecurityError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc

        return Response(_status_payload(video_request), status=status.HTTP_201_CREATED)


class CustomVideoCheckoutView(CustomVideoStudentAPIView):
    @extend_schema(request=None, responses={201: CustomVideoCheckoutResponseSerializer})
    def post(self, request, reference: str):
        try:
            video_request = CustomVideoRequest.objects.get(
                reference=reference,
                student=request.user.student,
            )
        except CustomVideoRequest.DoesNotExist:
            return Response(
                {"detail": "Custom-video request not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            checkout = create_custom_video_checkout(
                student=request.user.student,
                video_request=video_request,
            )
        except PaymentSecurityError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc

        video_request.refresh_from_db()
        return Response(
            {
                "request_reference": video_request.reference,
                "status": video_request.status,
                "gateway_url": checkout.gateway_url,
                "fields": checkout.fields,
                "amount": video_request.amount,
                "currency": video_request.currency,
            },
            status=status.HTTP_201_CREATED,
        )


class CustomVideoRequestStatusView(CustomVideoStudentAPIView):
    @extend_schema(responses={200: CustomVideoRequestResponseSerializer})
    def get(self, request, reference: str):
        try:
            video_request = CustomVideoRequest.objects.prefetch_related("supporting_files").get(
                reference=reference,
                student=request.user.student,
            )
        except CustomVideoRequest.DoesNotExist:
            return Response(
                {"detail": "Custom-video request not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(_status_payload(video_request))
