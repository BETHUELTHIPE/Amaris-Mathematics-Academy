"""Student browsing and approved tutor uploads with no public storage URLs."""

from botocore.exceptions import BotoCoreError, ClientError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.http import content_disposition_header
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import SupabaseStudentAuthentication
from .library_models import LibraryResource, validate_library_file
from .tutor_views import SupabaseTutorAuthentication


class LibraryWriteSerializer(serializers.ModelSerializer):
    is_published = serializers.BooleanField(default=True)

    class Meta:
        model = LibraryResource
        fields = (
            "title",
            "description",
            "resource_type",
            "subject",
            "level",
            "file",
            "sharing_permitted",
            "is_published",
        )

    def validate_file(self, value):
        try:
            validate_library_file(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return value

    def validate_sharing_permitted(self, value):
        if not value:
            raise serializers.ValidationError("Confirm permission to share this document with students.")
        return value

    def validate(self, attrs):
        if not attrs.get("sharing_permitted"):
            raise serializers.ValidationError({"sharing_permitted": "Confirm permission to share this document."})
        return attrs


class LibraryReadSerializer(serializers.ModelSerializer):
    can_manage = serializers.SerializerMethodField()

    class Meta:
        model = LibraryResource
        fields = (
            "id",
            "title",
            "description",
            "resource_type",
            "subject",
            "level",
            "original_name",
            "size_bytes",
            "content_type",
            "is_published",
            "created_at",
            "can_manage",
        )

    def get_can_manage(self, obj) -> bool:
        return self.context.get("tutor_id") == obj.uploaded_by_id and obj.uploaded_by_id is not None


class LibraryListResponseSerializer(serializers.Serializer):
    results = LibraryReadSerializer(many=True)
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()


class LibraryPublicationSerializer(serializers.Serializer):
    is_published = serializers.BooleanField()


class PrivateLibraryView(APIView):
    authentication_classes = (SupabaseStudentAuthentication,)
    permission_classes = (IsAuthenticated,)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        response["Vary"] = "Authorization"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    def visible_resources(self):
        return LibraryResource.objects.filter(is_published=True)

    def serializer_context(self):
        return {}


class LibraryListView(PrivateLibraryView):
    @extend_schema(responses=LibraryListResponseSerializer)
    def get(self, request):
        resources = self.visible_resources()
        query = request.query_params.get("q", "").strip()[:150]
        if query:
            resources = resources.filter(
                Q(title__icontains=query)
                | Q(description__icontains=query)
                | Q(subject__icontains=query)
                | Q(level__icontains=query)
            )
        kind = request.query_params.get("resource_type", "")
        if kind:
            resources = resources.filter(resource_type=kind)
        try:
            page = max(1, min(int(request.query_params.get("page", "1")), 100000))
        except ValueError:
            page = 1
        size = 24
        count = resources.count()
        rows = resources[(page - 1) * size : page * size]
        return Response(
            {
                "results": LibraryReadSerializer(rows, many=True, context=self.serializer_context()).data,
                "count": count,
                "page": page,
                "page_size": size,
            }
        )


class LibraryDownloadView(PrivateLibraryView):
    @extend_schema(responses={(200, "application/octet-stream"): bytes})
    def get(self, request, resource_id):
        resource = get_object_or_404(self.visible_resources(), pk=resource_id)
        storage = resource.file.storage
        try:
            if getattr(storage, "querystring_auth", False):
                # Existing private Supabase S3 storage signs URLs for five minutes.
                url = storage.url(
                    resource.file.name,
                    parameters={
                        "ResponseContentDisposition": content_disposition_header(True, resource.original_name),
                        "ResponseContentType": resource.content_type,
                    },
                )
                return HttpResponseRedirect(url)
            return FileResponse(
                resource.file.open("rb"),
                as_attachment=True,
                filename=resource.original_name,
                content_type=resource.content_type,
            )
        except (OSError, ValueError, BotoCoreError, ClientError) as exc:
            raise LibraryStorageUnavailable from exc


class LibraryStorageUnavailable(APIException):
    status_code = 503
    default_detail = "The Library file service is temporarily unavailable. Please try again."


class TutorLibraryMixin:
    authentication_classes = (SupabaseTutorAuthentication,)

    def visible_resources(self):
        return LibraryResource.objects.filter(Q(is_published=True) | Q(uploaded_by=self.request.user))

    def serializer_context(self):
        return {"tutor_id": self.request.user.pk}


class TutorLibraryView(TutorLibraryMixin, LibraryListView):
    parser_classes = (MultiPartParser, FormParser)

    @extend_schema(request=LibraryWriteSerializer, responses={201: LibraryReadSerializer})
    def post(self, request):
        serializer = LibraryWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                resource = serializer.save(uploaded_by=request.user)
        except (OSError, BotoCoreError, ClientError) as exc:
            raise LibraryStorageUnavailable from exc
        return Response(LibraryReadSerializer(resource, context=self.serializer_context()).data, status=201)


class TutorLibraryDownloadView(TutorLibraryMixin, LibraryDownloadView):
    pass


class TutorLibraryUpdateView(TutorLibraryMixin, PrivateLibraryView):
    parser_classes = (JSONParser,)

    @extend_schema(request=LibraryPublicationSerializer, responses=LibraryReadSerializer)
    def patch(self, request, resource_id):
        resource = get_object_or_404(LibraryResource, pk=resource_id, uploaded_by=request.user)
        serializer = LibraryPublicationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resource.is_published = serializer.validated_data["is_published"]
        resource.save(update_fields=["is_published", "updated_at"])
        return Response(LibraryReadSerializer(resource, context=self.serializer_context()).data)
