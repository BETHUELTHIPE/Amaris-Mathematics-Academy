from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.uploadhandler import FileUploadHandler, StopUpload
from django.db import DatabaseError
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from content.models import VideoAsset
from content.services.tutor_video_uploads import MAX_VIDEO_BYTES, UploadConflict, submit_video
from content.tutor_views import TutorOnlyAPIView


class TutorVideoThrottle(UserRateThrottle):
    scope = "tutor-video-upload"
    rate = "6/hour"


class VideoByteLimitHandler(FileUploadHandler):
    def __init__(self, request):
        super().__init__(request)
        self.total = 0

    def receive_data_chunk(self, raw_data, start):
        self.total += len(raw_data)
        if self.total > min(MAX_VIDEO_BYTES, settings.TUTOR_VIDEO_MAX_UPLOAD_BYTES):
            self.request.video_upload_limit_exceeded = True
            raise StopUpload(connection_reset=True)
        return raw_data

    def file_complete(self, file_size):
        return None


class TutorVideoInput(serializers.Serializer):
    idempotency_key = serializers.RegexField(r"^[A-Za-z0-9_-]{8,64}$")
    video_id = serializers.UUIDField(required=False)
    title = serializers.CharField(min_length=2, max_length=180)
    curriculum = serializers.ChoiceField(choices=VideoAsset._meta.get_field("curriculum").choices)
    subject = serializers.ChoiceField(choices=VideoAsset._meta.get_field("subject").choices)
    academic_level = serializers.CharField(min_length=1, max_length=100)
    topic = serializers.CharField(min_length=2, max_length=180)
    duration_seconds = serializers.IntegerField(min_value=0, max_value=86400, required=False, default=0)
    source_file = serializers.FileField()


class TutorVideoView(TutorOnlyAPIView):
    parser_classes = (MultiPartParser, FormParser)
    throttle_classes = (TutorVideoThrottle,)

    def get_throttles(self):
        return [TutorVideoThrottle()] if self.request.method == "POST" else [UserRateThrottle()]

    def initialize_request(self, request, *args, **kwargs):
        request.upload_handlers.insert(0, VideoByteLimitHandler(request))
        return super().initialize_request(request, *args, **kwargs)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(responses=dict)
    def get(self, request):
        return Response(
            {
                "results": [
                    {
                        "id": item.pk,
                        "title": item.title,
                        "curriculum": item.get_curriculum_display(),
                        "topic": item.topic,
                        "publication_status": "Published" if item.is_live else "Pending Admin review",
                    }
                    for item in VideoAsset.objects.filter(uploaded_by=request.user).order_by("-created_at")[:25]
                ]
            }
        )

    @extend_schema(request=TutorVideoInput, responses=dict)
    def post(self, request):
        if not settings.TUTOR_VIDEO_UPLOADS_ENABLED:
            return Response({"detail": "Tutor video submissions are not available yet."}, status=503)
        limit = min(MAX_VIDEO_BYTES, settings.TUTOR_VIDEO_MAX_UPLOAD_BYTES)
        try:
            length = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            return Response({"detail": "Invalid upload length."}, status=400)
        if length > limit + 65536:
            return Response({"detail": "The video exceeds the upload size limit."}, status=413)
        data = request.data
        if getattr(request._request, "video_upload_limit_exceeded", False):
            return Response({"detail": "The video exceeds the upload size limit."}, status=413)
        if set(request.FILES) != {"source_file"} or len(request.FILES.getlist("source_file")) != 1:
            return Response({"detail": "Submit exactly one video file."}, status=400)
        values = TutorVideoInput(data=data)
        values.is_valid(raise_exception=True)
        fields = dict(values.validated_data)
        key, upload, video_id = fields.pop("idempotency_key"), fields.pop("source_file"), fields.pop("video_id", None)
        try:
            event, created = submit_video(
                tutor=request.user, key=key, upload=upload, metadata=fields, video_id=video_id
            )
        except DjangoValidationError as exc:
            return Response({"detail": " ".join(exc.messages)}, status=400)
        except UploadConflict as exc:
            return Response({"detail": str(exc)}, status=409)
        except (OSError, DatabaseError, BotoCoreError, ClientError):
            return Response({"detail": "Upload temporarily unavailable. Retry with the same upload key."}, status=503)
        return Response(
            {
                "id": event.video_id,
                "activity_reference": event.pk,
                "publication_status": "Pending Admin review",
                "admin_alert_status": event.delivery_status,
            },
            status=201 if created else 200,
        )
