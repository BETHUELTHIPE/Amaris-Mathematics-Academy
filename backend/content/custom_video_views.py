from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import SupabaseStudentAuthentication
from .models import (
    CustomVideoInvoice,
    CustomVideoRequest,
    CustomVideoSettings,
    TutorAvailabilitySlot,
)
from .services.custom_videos import (
    CustomVideoValidationError,
    create_custom_video_checkout,
    create_custom_video_request,
)
from .services.payments import PaymentSecurityError


class CustomVideoOptionSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class CustomVideoOptionsResponseSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    pricing_configured = serializers.BooleanField()
    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        allow_null=True,
    )
    currency = serializers.CharField()
    max_files = serializers.IntegerField()
    max_file_size_mb = serializers.IntegerField()
    curricula = CustomVideoOptionSerializer(many=True)
    subjects = CustomVideoOptionSerializer(many=True)
    grades = CustomVideoOptionSerializer(many=True)
    topic_mode = serializers.CharField()
    modelled_topics = serializers.ListField(child=serializers.CharField())
    topic_note = serializers.CharField()


class CustomVideoOptionsView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(responses={200: CustomVideoOptionsResponseSerializer})
    def get(self, request):
        settings = CustomVideoSettings.objects.first()
        return Response(
            {
                "enabled": bool(settings and settings.enabled),
                "pricing_configured": bool(settings and settings.flat_fee is not None),
                "amount": settings.flat_fee if settings else None,
                "currency": settings.currency if settings else "ZAR",
                "max_files": settings.max_files if settings else 5,
                "max_file_size_mb": settings.max_file_size_mb if settings else 15,
                "curricula": [
                    {"value": value, "label": label}
                    for value, label in TutorAvailabilitySlot.Programme.choices
                ],
                "subjects": [
                    {"value": value, "label": label}
                    for value, label in TutorAvailabilitySlot.Subject.choices
                ],
                "grades": [
                    {"value": value, "label": label}
                    for value, label in CustomVideoRequest.Grade.choices
                ],
                "topic_mode": "free_text",
                "modelled_topics": [],
                "topic_note": (
                    "Enter the exact topic you need. Topic suggestions are only shown "
                    "when curriculum content is modelled in the academy catalogue."
                ),
            }
        )


class CustomVideoRequestCreateSerializer(serializers.Serializer):
    curriculum = serializers.ChoiceField(
        choices=TutorAvailabilitySlot.Programme.choices
    )
    subject = serializers.ChoiceField(choices=TutorAvailabilitySlot.Subject.choices)
    grade = serializers.ChoiceField(choices=CustomVideoRequest.Grade.choices)
    topic = serializers.CharField(min_length=2, max_length=220, trim_whitespace=True)
    idempotency_key = serializers.RegexField(r"^[A-Za-z0-9_-]{8,64}$")
    files = serializers.ListField(
        child=serializers.FileField(),
        allow_empty=False,
    )


class CustomVideoRequestResponseSerializer(serializers.Serializer):
    request_reference = serializers.CharField()
    status = serializers.CharField()
    curriculum = serializers.CharField()
    curriculum_label = serializers.CharField()
    subject = serializers.CharField()
    subject_label = serializers.CharField()
    grade = serializers.CharField()
    grade_label = serializers.CharField()
    topic = serializers.CharField()
    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        allow_null=True,
    )
    currency = serializers.CharField()
    attachment_count = serializers.IntegerField()
    invoice_number = serializers.CharField(allow_null=True)
    invoice_pdf_url = serializers.CharField(allow_blank=True)
    delivery_url = serializers.URLField(allow_blank=True)


class CustomVideoCheckoutResponseSerializer(serializers.Serializer):
    request_reference = serializers.CharField()
    status = serializers.CharField()
    gateway_url = serializers.URLField()
    fields = serializers.DictField(child=serializers.CharField())
    request = serializers.DictField()


def _request_payload(request_record: CustomVideoRequest) -> dict:
    try:
        invoice = request_record.invoice
    except CustomVideoInvoice.DoesNotExist:
        invoice = None
    invoice_url = ""
    if invoice is not None and invoice.pdf_file.name:
        try:
            invoice_url = invoice.pdf_file.url
        except (ValueError, OSError):
            invoice_url = ""

    return {
        "request_reference": request_record.reference,
        "status": request_record.status,
        "curriculum": request_record.curriculum,
        "curriculum_label": request_record.get_curriculum_display(),
        "subject": request_record.subject,
        "subject_label": request_record.get_subject_display(),
        "grade": request_record.grade,
        "grade_label": request_record.get_grade_display(),
        "topic": request_record.topic,
        "amount": request_record.amount,
        "currency": request_record.currency,
        "attachment_count": request_record.attachments.count(),
        "invoice_number": invoice.invoice_number if invoice is not None else None,
        "invoice_pdf_url": invoice_url,
        "delivery_url": (
            request_record.delivery_url
            if request_record.status == CustomVideoRequest.Status.DELIVERED
            else ""
        ),
    }


class CustomVideoStudentAPIView(APIView):
    authentication_classes = (SupabaseStudentAuthentication,)
    permission_classes = (IsAuthenticated,)

    @property
    def student(self):
        return self.request.user.student


class CustomVideoRequestCreateView(CustomVideoStudentAPIView):
    parser_classes = (MultiPartParser, FormParser)

    @extend_schema(
        request=CustomVideoRequestCreateSerializer,
        responses={201: CustomVideoRequestResponseSerializer},
    )
    def post(self, request):
        serializer = CustomVideoRequestCreateSerializer(
            data={
                "curriculum": request.data.get("curriculum"),
                "subject": request.data.get("subject"),
                "grade": request.data.get("grade"),
                "topic": request.data.get("topic"),
                "idempotency_key": request.data.get("idempotency_key"),
                "files": request.FILES.getlist("files"),
            }
        )
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data

        try:
            request_record = create_custom_video_request(
                student=request.user.student,
                curriculum=values["curriculum"],
                subject=values["subject"],
                grade=values["grade"],
                topic=values["topic"],
                idempotency_key=values["idempotency_key"],
                files=values["files"],
            )
        except CustomVideoValidationError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc

        return Response(
            _request_payload(request_record),
            status=status.HTTP_201_CREATED,
        )


class CustomVideoRequestStatusView(CustomVideoStudentAPIView):
    @extend_schema(responses={200: CustomVideoRequestResponseSerializer})
    def get(self, request, reference: str):
        try:
            request_record = (
                CustomVideoRequest.objects.select_related("invoice")
                .prefetch_related("attachments")
                .get(
                    reference=reference,
                    student=request.user.student,
                )
            )
        except CustomVideoRequest.DoesNotExist:
            return Response(
                {"detail": "Custom-video request not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(_request_payload(request_record))


class CustomVideoCheckoutView(CustomVideoStudentAPIView):
    @extend_schema(
        request=None,
        responses={201: CustomVideoCheckoutResponseSerializer},
    )
    def post(self, request, reference: str):
        try:
            request_record = CustomVideoRequest.objects.prefetch_related(
                "attachments"
            ).get(
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
                request_record=request_record,
            )
        except PaymentSecurityError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc

        request_record.refresh_from_db()
        return Response(
            {
                "request_reference": request_record.reference,
                "status": request_record.status,
                "gateway_url": checkout.gateway_url,
                "fields": checkout.fields,
                "request": {
                    "curriculum": request_record.get_curriculum_display(),
                    "subject": request_record.get_subject_display(),
                    "grade": request_record.get_grade_display(),
                    "topic": request_record.topic,
                    "amount": (
                        f"{request_record.amount:.2f}"
                        if request_record.amount is not None
                        else ""
                    ),
                    "currency": request_record.currency,
                    "attachment_count": request_record.attachments.count(),
                },
            },
            status=status.HTTP_201_CREATED,
        )
