from __future__ import annotations

from django.core.files.storage import storages
from django.http import FileResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .authentication import SupabaseStudentAuthentication
from .models import TutorAvailabilitySlot, VideoRequest
from .services.invoices import archive_invoice_pdf, student_invoice_key
from .services.payments import PaymentSecurityError
from .services.video_requests import (
    VIDEO_REQUEST_PRICES,
    create_video_request_checkout,
    register_resumable_document,
    video_request_eta,
    video_request_queue_position,
)


class VideoRequestCheckoutSerializer(serializers.Serializer):
    programme = serializers.ChoiceField(choices=TutorAvailabilitySlot.Programme.choices)
    subject = serializers.ChoiceField(choices=TutorAvailabilitySlot.Subject.choices)
    level = serializers.CharField(min_length=1, max_length=80, trim_whitespace=True)
    topic = serializers.CharField(min_length=2, max_length=180, trim_whitespace=True)
    request_type = serializers.ChoiceField(choices=VideoRequest.RequestType.choices)
    instructions = serializers.CharField(max_length=2000, allow_blank=True, required=False, trim_whitespace=True)
    explanation_style = serializers.CharField(
        max_length=120,
        allow_blank=True,
        required=False,
        trim_whitespace=True,
    )
    preferred_duration_minutes = serializers.IntegerField(min_value=15, max_value=180)
    idempotency_key = serializers.RegexField(r"^[A-Za-z0-9_-]{8,64}$")
    documents = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        allow_empty=True,
        max_length=5,
        write_only=True,
    )


class VideoRequestCheckoutResponseSerializer(serializers.Serializer):
    request_reference = serializers.CharField()
    status = serializers.CharField()
    gateway_url = serializers.URLField()
    fields = serializers.DictField(child=serializers.CharField())
    request = serializers.DictField()


class VideoRequestStatusSerializer(serializers.Serializer):
    request_reference = serializers.CharField()
    ticket_number = serializers.CharField(allow_blank=True, allow_null=True)
    status = serializers.CharField()
    status_label = serializers.CharField()
    request_type = serializers.CharField()
    request_type_label = serializers.CharField()
    programme = serializers.CharField()
    subject = serializers.CharField()
    level = serializers.CharField()
    topic = serializers.CharField()
    preferred_duration_minutes = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField()
    tutor = serializers.CharField()
    requests_ahead = serializers.IntegerField(allow_null=True)
    queue_position = serializers.IntegerField(allow_null=True)
    estimated_ready_from = serializers.DateField(allow_null=True)
    estimated_ready_to = serializers.DateField(allow_null=True)
    invoice_number = serializers.CharField(allow_blank=True, allow_null=True)
    invoice_ready = serializers.BooleanField()
    document_count = serializers.IntegerField()
    document_upload_prefix = serializers.CharField(allow_blank=True, required=False)
    video = serializers.DictField(allow_null=True)


class VideoRequestPackageResponseSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField()


def _status_payload(request: VideoRequest) -> dict:
    position = video_request_queue_position(request)
    eta_from, eta_to = video_request_eta(request)
    video = None
    if request.status == VideoRequest.Status.READY and request.video_external_id:
        video = {
            "provider": request.video_provider,
            "youtube_video_id": (
                request.video_external_id if request.video_provider == VideoRequest.VideoProvider.YOUTUBE else ""
            ),
            "direct_download_url": (
                f"/api/v1/student/video-requests/{request.reference}/video/"
                if request.video_provider == VideoRequest.VideoProvider.DIRECT
                else ""
            ),
        }
    return {
        "request_reference": request.reference,
        "ticket_number": request.ticket_number,
        "status": request.status,
        "status_label": request.get_status_display(),
        "request_type": request.request_type,
        "request_type_label": request.get_request_type_display(),
        "programme": request.get_programme_display(),
        "subject": request.get_subject_display(),
        "level": request.level,
        "topic": request.topic,
        "preferred_duration_minutes": request.preferred_duration_minutes,
        "amount": request.amount,
        "currency": request.currency,
        "tutor": request.tutor_display_name,
        "requests_ahead": position - 1 if position else None,
        "queue_position": position,
        "estimated_ready_from": eta_from,
        "estimated_ready_to": eta_to,
        "invoice_number": request.invoice_number,
        "invoice_ready": bool(request.invoice_number and request.confirmation_sent_at),
        "document_count": request.documents.count(),
        "document_upload_prefix": (
            f"{request.student.supabase_user_id}/video-requests/{request.pk}/documents/"
            if request.status == VideoRequest.Status.PENDING_PAYMENT else ""
        ),
        "video": video,
    }


class VideoRequestStudentAPIView(APIView):
    authentication_classes = (SupabaseStudentAuthentication,)
    permission_classes = (IsAuthenticated,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "video_requests"

    @property
    def student(self):
        return self.request.user.student

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class VideoRequestCheckoutView(VideoRequestStudentAPIView):
    parser_classes = (MultiPartParser, FormParser)

    @extend_schema(
        request=VideoRequestCheckoutSerializer,
        responses={201: VideoRequestCheckoutResponseSerializer},
    )
    def post(self, request):
        data = request.data.copy()
        if hasattr(data, "setlist"):
            data.setlist("documents", request.FILES.getlist("documents"))
        serializer = VideoRequestCheckoutSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        try:
            checkout = create_video_request_checkout(
                student=self.student,
                programme=values["programme"],
                subject=values["subject"],
                level=values["level"],
                topic=values["topic"],
                request_type=values["request_type"],
                instructions=values.get("instructions", ""),
                explanation_style=values.get("explanation_style", ""),
                preferred_duration_minutes=values["preferred_duration_minutes"],
                idempotency_key=values["idempotency_key"],
                documents=values.get("documents", ()),
            )
        except PaymentSecurityError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        except OSError:
            return Response(
                {"detail": "Private document storage is temporarily unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        video_request = VideoRequest.objects.get(reference=checkout.request_reference)
        return Response(
            {
                "request_reference": video_request.reference,
                "document_upload_prefix": (
                    f"{video_request.student.supabase_user_id}/video-requests/{video_request.pk}/documents/"
                ),
                "status": video_request.status,
                "gateway_url": checkout.gateway_url,
                "fields": checkout.fields,
                "request": {
                    "request_type": video_request.get_request_type_display(),
                    "programme": video_request.get_programme_display(),
                    "subject": video_request.get_subject_display(),
                    "level": video_request.level,
                    "topic": video_request.topic,
                    "preferred_duration_minutes": video_request.preferred_duration_minutes,
                    "amount": f"{video_request.amount:.2f}",
                    "currency": video_request.currency,
                },
            },
            status=status.HTTP_201_CREATED,
        )



class ResumableDocumentSerializer(serializers.Serializer):
    storage_path = serializers.CharField(max_length=512)
    original_name = serializers.CharField(max_length=255)
    content_type = serializers.ChoiceField(choices=("application/pdf", "image/jpeg", "image/png"))
    size_bytes = serializers.IntegerField(min_value=1, max_value=1024 * 1024 * 1024)


class VideoRequestDocumentRegisterView(VideoRequestStudentAPIView):
    """Register metadata only after verifying the uploaded object in private Supabase S3."""

    @extend_schema(request=ResumableDocumentSerializer, responses={201: OpenApiTypes.OBJECT})
    def post(self, request, reference: str):
        serializer = ResumableDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            document = register_resumable_document(
                student=self.student,
                reference=reference,
                **serializer.validated_data,
            )
        except PaymentSecurityError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        except OSError:
            return Response(
                {"detail": "Private document storage is unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(
            {"id": document.pk, "size_bytes": document.size_bytes},
            status=status.HTTP_201_CREATED,
        )


class VideoRequestListView(VideoRequestStudentAPIView):
    @extend_schema(responses={200: VideoRequestStatusSerializer(many=True)})
    def get(self, request):
        requests = (
            VideoRequest.objects.filter(student=self.student)
            .select_related("assigned_tutor")
            .prefetch_related("documents")[:100]
        )
        return Response([_status_payload(item) for item in requests])


class VideoRequestStatusView(VideoRequestStudentAPIView):
    @extend_schema(
        responses={
            200: VideoRequestStatusSerializer,
            404: OpenApiResponse(description="Video request not found for this student."),
        }
    )
    def get(self, request, reference: str):
        try:
            item = (
                VideoRequest.objects.select_related("assigned_tutor")
                .prefetch_related("documents")
                .get(reference=reference, student=self.student)
            )
        except VideoRequest.DoesNotExist:
            return Response({"detail": "Video request not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_status_payload(item))


class VideoRequestInvoiceDownloadView(VideoRequestStudentAPIView):
    @extend_schema(
        responses={
            (200, "application/pdf"): OpenApiTypes.BINARY,
            404: OpenApiResponse(description="Invoice not found for this student."),
            503: OpenApiResponse(description="Invoice storage is temporarily unavailable."),
        }
    )
    def get(self, request, reference: str):
        item = VideoRequest.objects.filter(
            reference=reference,
            student=self.student,
            gateway_verified_at__isnull=False,
        ).first()
        if item is None or not item.invoice_number:
            return Response({"detail": "Invoice not found."}, status=status.HTTP_404_NOT_FOUND)
        key = student_invoice_key(item.student.supabase_user_id, item.invoice_number)
        storage = storages["student_private"]
        if not storage.exists(key):
            try:
                archive_invoice_pdf(item)
            except OSError:
                return Response(
                    {"detail": "Invoice is temporarily unavailable."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
        try:
            document = storage.open(key, "rb")
        except (OSError, ValueError):
            return Response(
                {"detail": "Invoice is temporarily unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        response = FileResponse(document, as_attachment=True, filename=f"{item.invoice_number}.pdf")
        response["Cache-Control"] = "private, no-store"
        return response


class VideoRequestVideoDownloadView(VideoRequestStudentAPIView):
    @extend_schema(
        responses={
            (200, "video/mp4"): OpenApiTypes.BINARY,
            404: OpenApiResponse(description="Completed video not found for this student."),
        }
    )
    def get(self, request, reference: str):
        item = VideoRequest.objects.filter(
            reference=reference,
            student=self.student,
            status=VideoRequest.Status.READY,
            video_provider=VideoRequest.VideoProvider.DIRECT,
        ).first()
        if item is None or not item.video_external_id:
            return Response({"detail": "Completed video not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            video = storages["student_private"].open(item.video_external_id, "rb")
        except (OSError, ValueError):
            return Response({"detail": "Completed video not found."}, status=status.HTTP_404_NOT_FOUND)
        response = FileResponse(video, content_type="video/mp4")
        response["Content-Disposition"] = "inline"
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class VideoRequestPackageView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(responses={200: VideoRequestPackageResponseSerializer(many=True)}, auth=[])
    def get(self, request):
        del request
        return Response(
            [
                {
                    "value": value,
                    "label": label,
                    "amount": f"{VIDEO_REQUEST_PRICES[value]:.2f}",
                    "currency": "ZAR",
                }
                for value, label in VideoRequest.RequestType.choices
            ]
        )
