from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import SupabaseStudentAuthentication
from .models import TutorAvailabilitySlot, VideoRequest
from .services.payments import PaymentSecurityError
from .services.video_requests import VIDEO_REQUEST_PRICE, create_video_request_checkout


class VideoRequestInfoSerializer(serializers.Serializer):
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField()
    programmes = serializers.ListField(child=serializers.DictField())
    subjects = serializers.ListField(child=serializers.DictField())


class VideoRequestInfoView(APIView):
    """Public pricing + option metadata so the browser never owns the price."""

    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(responses={200: VideoRequestInfoSerializer})
    def get(self, request):
        return Response(
            {
                "price": f"{VIDEO_REQUEST_PRICE:.2f}",
                "currency": "ZAR",
                "programmes": [
                    {"value": value, "label": label}
                    for value, label in TutorAvailabilitySlot.Programme.choices
                ],
                "subjects": [
                    {"value": value, "label": label}
                    for value, label in TutorAvailabilitySlot.Subject.choices
                ],
            }
        )


class VideoRequestCheckoutRequestSerializer(serializers.Serializer):
    programme = serializers.ChoiceField(choices=TutorAvailabilitySlot.Programme.choices)
    subject = serializers.ChoiceField(choices=TutorAvailabilitySlot.Subject.choices)
    level = serializers.CharField(min_length=1, max_length=80, trim_whitespace=True)
    topic = serializers.CharField(min_length=2, max_length=180, trim_whitespace=True)
    details = serializers.CharField(max_length=2000, required=False, allow_blank=True, trim_whitespace=True)
    idempotency_key = serializers.RegexField(r"^[A-Za-z0-9_-]{8,64}$")


class VideoRequestCheckoutResponseSerializer(serializers.Serializer):
    request_reference = serializers.CharField()
    status = serializers.CharField()
    gateway_url = serializers.URLField()
    fields = serializers.DictField(child=serializers.CharField())
    request = serializers.DictField()


class VideoRequestStatusSerializer(serializers.Serializer):
    request_reference = serializers.CharField()
    status = serializers.CharField()
    programme = serializers.CharField()
    subject = serializers.CharField()
    level = serializers.CharField()
    topic = serializers.CharField()
    details = serializers.CharField(allow_blank=True)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField()
    invoice_number = serializers.CharField(allow_blank=True, allow_null=True)
    video = serializers.DictField(allow_null=True)


class VideoRequestStudentAPIView(APIView):
    authentication_classes = (SupabaseStudentAuthentication,)
    permission_classes = (IsAuthenticated,)

    @property
    def student(self):
        return self.request.user.student


def _video_payload(request_obj: VideoRequest) -> dict | None:
    """Release video access only from the fulfilled, verified backend state."""
    if request_obj.status != VideoRequest.Status.FULFILLED or request_obj.video is None:
        return None
    video = request_obj.video
    payload = {
        "title": video.title,
        "provider": video.provider,
        "duration_seconds": video.duration_seconds,
    }
    if video.provider == video.Provider.YOUTUBE:
        payload["youtube_video_id"] = video.youtube_video_id
        payload["youtube_url"] = video.youtube_url
    elif video.provider == video.Provider.VIMEO:
        payload["vimeo_video_id"] = video.vimeo_video_id
        payload["vimeo_hash"] = video.vimeo_hash
    return payload


class VideoRequestCheckoutView(VideoRequestStudentAPIView):
    @extend_schema(
        request=VideoRequestCheckoutRequestSerializer,
        responses={201: VideoRequestCheckoutResponseSerializer},
    )
    def post(self, request):
        serializer = VideoRequestCheckoutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        try:
            checkout = create_video_request_checkout(
                student=request.user.student,
                programme=values["programme"],
                subject=values["subject"],
                level=values["level"],
                topic=values["topic"],
                details=values.get("details", ""),
                idempotency_key=values["idempotency_key"],
            )
        except PaymentSecurityError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc

        request_obj = VideoRequest.objects.get(reference=checkout.request_reference)
        return Response(
            {
                "request_reference": request_obj.reference,
                "status": request_obj.status,
                "gateway_url": checkout.gateway_url,
                "fields": checkout.fields,
                "request": {
                    "programme": request_obj.get_programme_display(),
                    "subject": request_obj.get_subject_display(),
                    "level": request_obj.level,
                    "topic": request_obj.topic,
                    "details": request_obj.details,
                    "amount": f"{request_obj.amount:.2f}",
                    "currency": request_obj.currency,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class VideoRequestStatusView(VideoRequestStudentAPIView):
    @extend_schema(responses={200: VideoRequestStatusSerializer})
    def get(self, request, reference: str):
        try:
            request_obj = VideoRequest.objects.select_related("video").get(
                reference=reference,
                student=request.user.student,
            )
        except VideoRequest.DoesNotExist:
            return Response(
                {"detail": "Video request not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "request_reference": request_obj.reference,
                "status": request_obj.status,
                "programme": request_obj.get_programme_display(),
                "subject": request_obj.get_subject_display(),
                "level": request_obj.level,
                "topic": request_obj.topic,
                "details": request_obj.details,
                "amount": request_obj.amount,
                "currency": request_obj.currency,
                "invoice_number": request_obj.invoice_number,
                "video": _video_payload(request_obj),
            }
        )
