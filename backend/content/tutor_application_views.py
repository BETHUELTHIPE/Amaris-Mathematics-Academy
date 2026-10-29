"""Verified applicants may submit once and view only their own recruitment record."""

import uuid
from dataclasses import dataclass

from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.db import IntegrityError, transaction
from django.http import FileResponse
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed, NotFound
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from .authentication import SupabaseStudentAuthentication
from .models import TutorApplication, TutorApplicationDocument
from .services.payments import PaymentSecurityError
from .services.tutor_applications import deliver_application_acknowledgement
from .services.video_requests import validate_documents

REQUIRED_TUTOR_DOCUMENTS = (
    ("document_id", "id", "Identity document"),
    ("document_cv", "cv", "Curriculum vitae"),
    ("document_matric", "matric", "Matric certificate"),
    ("document_academic", "academic", "Academic records"),
    ("document_tertiary", "tertiary", "Tertiary certificate"),
    ("document_other", "other", "Additional document"),
)
MAX_TUTOR_DOCUMENT_SIZE = 5 * 1024 * 1024
MAX_TUTOR_UPLOAD_TOTAL = 30 * 1024 * 1024


@dataclass(frozen=True)
class Applicant:
    id: uuid.UUID
    email: str
    is_authenticated: bool = True

    @property
    def pk(self):
        return self.id


class ApplicantAuthentication(BaseAuthentication):
    def authenticate(self, request):
        header = get_authorization_header(request).split()
        if not header:
            return None
        if len(header) != 2 or header[0].lower() != b"bearer":
            raise AuthenticationFailed("Sign in with a verified account to apply.")
        try:
            token = header[1].decode("ascii")
        except UnicodeDecodeError as exc:
            raise AuthenticationFailed("Invalid applicant session.") from exc
        # Authoritative Auth server validation; no role claims or synthetic student bypass.
        payload = SupabaseStudentAuthentication()._validate_token(token)
        if not payload.get("email_confirmed_at") or not payload.get("email"):
            raise AuthenticationFailed("Verify your email before applying.")
        try:
            user_id = uuid.UUID(str(payload.get("id")))
        except ValueError as exc:
            raise AuthenticationFailed("Invalid applicant identity.") from exc
        return Applicant(user_id, str(payload["email"]).strip().lower()), None

    def authenticate_header(self, request):
        return "Bearer"


class ApplicantThrottle(SimpleRateThrottle):
    rate = "30/hour"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": "tutor-applications", "ident": str(request.user.pk)}


class ApplicationInput(serializers.Serializer):
    full_name = serializers.CharField(max_length=160, min_length=2)
    phone = serializers.RegexField(r"^\+?[0-9 ()-]{7,30}$", max_length=30)
    location = serializers.CharField(max_length=500, min_length=2, required=False)
    country = serializers.CharField(max_length=2, required=False, allow_blank=True)
    province = serializers.CharField(max_length=160, required=False, allow_blank=True)
    city = serializers.CharField(max_length=160, required=False, allow_blank=True)
    provinceOther = serializers.CharField(max_length=160, required=False, allow_blank=True, write_only=True)
    cityOther = serializers.CharField(max_length=160, required=False, allow_blank=True, write_only=True)
    qualification = serializers.CharField(max_length=200, min_length=2)
    institution = serializers.CharField(max_length=200, min_length=2)
    subjects = serializers.CharField(max_length=300, min_length=2)
    programmes = serializers.ListField(
        child=serializers.ChoiceField(choices=["caps", "ieb", "tvet", "university"]), min_length=1, max_length=4
    )
    levels = serializers.CharField(max_length=200, min_length=2)
    experience_years = serializers.IntegerField(min_value=0, max_value=80)
    teaching_experience = serializers.CharField(max_length=4000, min_length=10)
    availability = serializers.CharField(max_length=2000, min_length=10)
    motivation = serializers.CharField(max_length=4000, min_length=20)
    consent = serializers.BooleanField()
    documents = serializers.ListField(
        child=serializers.FileField(), min_length=1, max_length=5, write_only=True, required=False
    )
    document_id = serializers.FileField(required=False, write_only=True)
    document_cv = serializers.FileField(required=False, write_only=True)
    document_matric = serializers.FileField(required=False, write_only=True)
    document_academic = serializers.FileField(required=False, write_only=True)
    document_tertiary = serializers.FileField(required=False, write_only=True)
    document_other = serializers.FileField(required=False, write_only=True)

    def validate(self, attrs):
        from .locations import COUNTRY_NAMES, normalize_location

        attrs = normalize_location(attrs)
        present = [name for name, _category, _label in REQUIRED_TUTOR_DOCUMENTS if name in attrs]
        legacy = bool(attrs.get("documents"))
        require_categories = getattr(settings, "TUTOR_REQUIRE_SIX_DOCUMENTS", False)
        if present or require_categories:
            missing = {
                name: ["This document is required."]
                for name, _category, _label in REQUIRED_TUTOR_DOCUMENTS
                if name not in attrs
            }
            if missing:
                raise serializers.ValidationError(missing)
            if legacy:
                raise serializers.ValidationError({"documents": "Use the six named document upload fields instead."})
        elif not legacy:
            raise serializers.ValidationError(
                {name: ["This document is required."] for name, _category, _label in REQUIRED_TUTOR_DOCUMENTS}
            )
        if attrs.get("country"):
            attrs["location"] = ", ".join((attrs["city"], attrs["province"], COUNTRY_NAMES[attrs["country"]]))
        elif not attrs.get("location"):
            raise serializers.ValidationError(
                {
                    "country": "Please choose your country.",
                    "province": "Please choose your province or region.",
                    "city": "Please choose your city or town.",
                }
            )
        return attrs

    def validate_consent(self, value):
        if value is not True:
            raise serializers.ValidationError("Confirm the recruitment privacy notice and declaration.")
        return value


class DocumentOutput(serializers.Serializer):
    id = serializers.UUIDField()
    category = serializers.CharField()
    original_name = serializers.CharField()
    size_bytes = serializers.IntegerField()


class ApplicationOutput(serializers.ModelSerializer):
    reference = serializers.CharField(read_only=True)
    documents = DocumentOutput(many=True, read_only=True)

    class Meta:
        model = TutorApplication
        fields = ("reference", "status", "submitted_at", "acknowledgement_sent_at", "documents")


class ApplicationEnvelope(serializers.Serializer):
    application = ApplicationOutput(allow_null=True)


class ApplicantAPIView(APIView):
    authentication_classes = (ApplicantAuthentication,)
    permission_classes = (IsAuthenticated,)
    throttle_classes = (ApplicantThrottle,)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        response["Vary"] = "Authorization"
        return response


def _existing(user_id):
    return TutorApplication.objects.prefetch_related("documents").filter(supabase_user_id=user_id).first()


class TutorApplicationView(ApplicantAPIView):
    parser_classes = (MultiPartParser, FormParser)

    @extend_schema(responses=ApplicationEnvelope)
    def get(self, request):
        application = _existing(request.user.id)
        return Response({"application": ApplicationOutput(application).data if application else None})

    @extend_schema(request=ApplicationInput, responses={201: ApplicationEnvelope, 200: ApplicationEnvelope})
    def post(self, request):
        existing = _existing(request.user.id)
        if existing:
            # A lost response or double click never creates a duplicate or sends another acknowledgement.
            return Response({"application": ApplicationOutput(existing).data})
        serializer = ApplicationInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        attrs = dict(serializer.validated_data)
        attrs.pop("consent")
        # During a staged rollout the existing generic form remains supported.
        # Set TUTOR_REQUIRE_SIX_DOCUMENTS=True after the new six-field frontend goes live.
        labeled = [
            (name, category, attrs.pop(name)) for name, category, _label in REQUIRED_TUTOR_DOCUMENTS if name in attrs
        ]
        legacy_uploads = attrs.pop("documents", [])
        if labeled:
            if sum(upload.size for _name, _category, upload in labeled) > MAX_TUTOR_UPLOAD_TOTAL:
                raise serializers.ValidationError({"documents": "Six files may total no more than 30 MB."})
            invalid = {
                name: ["Each file must be between 1 byte and 5 MB."]
                for name, _category, upload in labeled
                if not 0 < upload.size <= MAX_TUTOR_DOCUMENT_SIZE
            }
            if invalid:
                raise serializers.ValidationError(invalid)
        elif sum(upload.size for upload in legacy_uploads) > 15 * 1024 * 1024 or any(
            upload.size > MAX_TUTOR_DOCUMENT_SIZE for upload in legacy_uploads
        ):
            raise serializers.ValidationError({"documents": "Use up to five files, 5 MB each and 15 MB total."})
        try:
            typed_documents = (
                [(category, validate_documents([upload])[0]) for _name, category, upload in labeled]
                if labeled
                else [("legacy", document) for document in validate_documents(legacy_uploads)]
            )
        except PaymentSecurityError as exc:
            raise serializers.ValidationError({"documents": str(exc)}) from exc
        storage = storages["tutor_qualifications"]
        saved = []
        # S3 uploads can take longer than the database idle-in-transaction timeout.
        # Stage objects before opening a short database transaction, then publish
        # the application and all six document records atomically.
        application_id = uuid.uuid4()
        staged = []
        try:
            for category, document in typed_documents:
                key = f"tutor-applications/{request.user.id}/{application_id}/{uuid.uuid4().hex}{document.extension}"
                path = storage.save(key, ContentFile(document.data))
                saved.append(path)
                staged.append((category, document, path))
            with transaction.atomic():
                application = TutorApplication.objects.create(
                    id=application_id, supabase_user_id=request.user.id, email=request.user.email, **attrs
                )
                for category, document, path in staged:
                    TutorApplicationDocument.objects.create(
                        application=application,
                        category=category,
                        storage_path=path,
                        original_name=document.original_name[:200],
                        content_type=document.content_type,
                        size_bytes=len(document.data),
                        sha256=document.sha256,
                    )
        except Exception as exc:
            for path in saved:
                try:
                    storage.delete(path)
                except Exception:
                    # Opaque object keys only; no qualifications, names or credentials in logs.
                    import logging

                    logging.getLogger(__name__).error("tutor_application_upload_cleanup_failed")
            if isinstance(exc, IntegrityError):
                existing = _existing(request.user.id)
                if existing:
                    return Response({"application": ApplicationOutput(existing).data})
                raise
            if isinstance(exc, (OSError, BotoCoreError, ClientError)):
                return Response({"detail": "Documents could not be stored. Please retry."}, status=503)
            raise
        # Commit documents before contacting SMTP; an outage never loses a submitted application.
        deliver_application_acknowledgement(application.pk)
        application.refresh_from_db()
        # Durable pending timestamp is the outbox. Beat/management command recovers a failed enqueue.
        from .tasks import deliver_tutor_application_acknowledgements

        try:
            deliver_tutor_application_acknowledgements.delay()
        except Exception:
            import logging

            logging.getLogger(__name__).warning("tutor_application_acknowledgement_enqueue_pending")
        return Response({"application": ApplicationOutput(application).data}, status=status.HTTP_201_CREATED)


class TutorApplicationAcknowledgementView(ApplicantAPIView):
    @extend_schema(request=None, responses=ApplicationEnvelope)
    def post(self, request):
        application = _existing(request.user.id)
        if application is None:
            raise NotFound()
        deliver_application_acknowledgement(application.pk)
        application.refresh_from_db()
        return Response({"application": ApplicationOutput(application).data})


class TutorApplicationDocumentView(ApplicantAPIView):
    @extend_schema(responses={(200, "application/octet-stream"): bytes})
    def get(self, request, document_id):
        document = TutorApplicationDocument.objects.filter(
            pk=document_id, application__supabase_user_id=request.user.id
        ).first()
        if not document:
            raise NotFound()
        return private_document_response(document)


def private_document_response(document):
    try:
        # Never return a public storage URL. Download only after object-level authorization.
        stream = storages["tutor_qualifications"].open(document.storage_path, "rb")
    except (OSError, BotoCoreError, ClientError):
        raise NotFound("Document unavailable.") from None
    response = FileResponse(
        stream, as_attachment=True, filename=document.original_name, content_type="application/octet-stream"
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "sandbox"
    return response
