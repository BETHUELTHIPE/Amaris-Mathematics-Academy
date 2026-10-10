"""JSON control plane for private direct-to-storage uploads; never receives file bytes."""

from botocore.exceptions import BotoCoreError, ClientError
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from .video_request_views import VideoRequestStudentAPIView
from .video_uploads import abort_upload, begin_upload, complete_upload, part_url


class VideoRequestMultipartUploadView(VideoRequestStudentAPIView):
    parser_classes = (JSONParser,)
    throttle_scope = "video_uploads"

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, reference):
        values = request.data
        if not isinstance(values, dict):
            raise serializers.ValidationError("Expected JSON upload metadata.")
        action = values.get("action")
        operations = {
            "init": begin_upload,
            "part": part_url,
            "complete": complete_upload,
            "abort": abort_upload,
        }
        if action not in operations:
            raise serializers.ValidationError("Unsupported upload operation.")
        try:
            result = operations[action](self.student, reference, values)
        except (ClientError, BotoCoreError, OSError):
            return Response(
                {"detail": "Private uploads are temporarily unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(result, headers={"Cache-Control": "private, no-store"})
