"""Private tutor video submissions. Django Admin controls publication."""

import uuid
from urllib.error import URLError

from botocore.exceptions import BotoCoreError, ClientError
from django.core.exceptions import ValidationError
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from .models import VideoAsset
from .services.course_media import MAX_BYTES, begin_video_upload, enabled_providers, verify_video_upload
from .tutor_views import TutorOnlyAPIView


class TutorMediaAPIView(TutorOnlyAPIView):
    parser_classes = (JSONParser,)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class UploadStartThrottle(UserRateThrottle):
    scope = "tutor_media_start"
    rate = "20/hour"


class UploadStartSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=("s3", "vimeo"))
    filename = serializers.CharField(max_length=255)
    title = serializers.CharField(max_length=180)
    size = serializers.IntegerField(min_value=1, max_value=MAX_BYTES)


class UploadFinishSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=("s3", "vimeo"))
    submission = serializers.UUIDField()
    ticket = serializers.CharField(max_length=1800)


class TutorVideoSerializer(serializers.ModelSerializer):
    ready = serializers.BooleanField(source="is_live")

    class Meta:
        model = VideoAsset
        fields = ("id", "title", "provider", "ready")


class TutorVideoUploadView(TutorMediaAPIView):
    @extend_schema(
        responses=inline_serializer(
            name="TutorLessonVideos",
            fields={
                "providers": serializers.DictField(child=serializers.BooleanField()),
                "videos": TutorVideoSerializer(many=True),
            },
        )
    )
    def get(self, request):
        videos = VideoAsset.objects.filter(submitted_by=request.user).order_by("-created_at", "-id")[:25]
        return Response({"providers": enabled_providers(), "videos": TutorVideoSerializer(videos, many=True).data})


class TutorVideoUploadStartView(TutorMediaAPIView):
    throttle_classes = (UploadStartThrottle,)

    @extend_schema(request=UploadStartSerializer, responses=serializers.DictField)
    def post(self, request):
        serializer = UploadStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        submission = uuid.uuid4()
        try:
            payload = begin_video_upload(
                user_id=request.user.pk, asset_id=submission, scope="tutor", **serializer.validated_data
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=status.HTTP_400_BAD_REQUEST)
        except (BotoCoreError, ClientError, URLError, TimeoutError, ValueError):
            return Response(
                {"detail": "The upload provider is temporarily unavailable."}, status=status.HTTP_502_BAD_GATEWAY
            )
        return Response({**payload, "submission": submission}, status=status.HTTP_201_CREATED)


class TutorVideoUploadFinishView(TutorMediaAPIView):
    @extend_schema(request=UploadFinishSerializer, responses={200: TutorVideoSerializer, 201: TutorVideoSerializer})
    def post(self, request):
        serializer = UploadFinishSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket, submission, provider = (serializer.validated_data[key] for key in ("ticket", "submission", "provider"))
        existing = VideoAsset.objects.filter(pk=submission, submitted_by=request.user, provider=provider).first()
        if existing:
            return Response(TutorVideoSerializer(existing).data)
        try:
            reference, title = verify_video_upload(
                ticket, user_id=request.user.pk, asset_id=submission, provider=provider, scope="tutor"
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=status.HTTP_400_BAD_REQUEST)
        field = "aws_media_key" if provider == "s3" else "vimeo_video_id"
        asset, created = VideoAsset.objects.get_or_create(
            pk=submission,
            defaults={"title": title, "provider": provider, "submitted_by": request.user, field: reference},
        )
        if asset.submitted_by_id != request.user.pk or asset.provider != provider:
            return Response(
                {"detail": "The upload does not match this submission."}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response(
            TutorVideoSerializer(asset).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )
