from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DatabaseError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from content.services.tutor_personnel import archived_pdf, submit_form
from content.services.tutor_video_uploads import UploadConflict
from content.tutor_personnel_models import TutorPersonnelForm
from content.tutor_views import TutorOnlyAPIView


class PersonnelInput(serializers.Serializer):
    idempotency_key = serializers.RegexField(r"^[A-Za-z0-9_-]{8,64}$")
    kind = serializers.ChoiceField(choices=TutorPersonnelForm.Kind.choices)
    leave_type = serializers.ChoiceField(choices=TutorPersonnelForm.LeaveType.choices, required=False)
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    last_teaching_day = serializers.DateField(required=False)
    reason = serializers.CharField(min_length=10, max_length=3000)
    handover = serializers.CharField(min_length=10, max_length=3000)
    contact_phone = serializers.RegexField(r"^\+?[0-9 ()-]{7,25}$")
    signature_name = serializers.CharField(min_length=2, max_length=150)
    declaration = serializers.BooleanField()

    def validate(self, data):
        if data["declaration"] is not True:
            raise serializers.ValidationError("Confirm the declaration before submitting.")
        if data["kind"] == "leave":
            if not all(data.get(key) for key in ("start_date", "end_date", "leave_type")):
                raise serializers.ValidationError("Choose a leave type and both leave dates.")
            if data["end_date"] < data["start_date"]:
                raise serializers.ValidationError("The last leave date cannot be before the first date.")
            if (data["end_date"] - data["start_date"]).days > 365:
                raise serializers.ValidationError("Use a leave period of no more than 366 calendar days.")
            if "last_teaching_day" in data:
                raise serializers.ValidationError("A leave form cannot contain a resignation date.")
        else:
            if not data.get("last_teaching_day"):
                raise serializers.ValidationError("Choose your proposed last teaching day.")
            if data["last_teaching_day"] < timezone.localdate():
                raise serializers.ValidationError("The proposed last teaching day must be today or later.")
            if any(key in data for key in ("start_date", "end_date", "leave_type")):
                raise serializers.ValidationError("A resignation form cannot contain leave dates or a leave type.")
        return data


class PersonnelThrottle(UserRateThrottle):
    scope = "tutor-personnel"
    rate = "10/hour"


def summary(item):
    return {
        "id": str(item.pk),
        "kind": item.kind,
        "form_type": item.get_kind_display(),
        "created_at": item.created_at,
        "status": item.get_status_display(),
        "review_notes": item.review_notes,
        "reviewed_at": item.reviewed_at,
        "details": item.payload,
        "pdf_path": f"/api/tutor/forms/{item.pk}/pdf",
    }


def pdf_response(item):
    response = HttpResponse(archived_pdf(item), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="amaris-{item.kind}-{item.pk}.pdf"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


class PrivateTutorFormsAPIView(TutorOnlyAPIView):
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class TutorPersonnelFormsView(PrivateTutorFormsAPIView):
    parser_classes = (JSONParser,)

    def get_throttles(self):
        return [PersonnelThrottle()] if self.request.method == "POST" else [UserRateThrottle()]

    @extend_schema(responses=dict)
    def get(self, request):
        try:
            page = max(1, min(int(request.query_params.get("page", "1")), 100000))
        except ValueError:
            return Response({"detail": "Choose a valid page number."}, status=400)
        rows = list(TutorPersonnelForm.objects.filter(tutor=request.user)[(page - 1) * 10 : page * 10 + 1])
        return Response({"results": [summary(item) for item in rows[:10]], "page": page, "has_more": len(rows) > 10})

    @extend_schema(request=PersonnelInput, responses=dict)
    def post(self, request):
        if not settings.TUTOR_PERSONNEL_FORMS_ENABLED:
            return Response({"detail": "Tutor forms are not available yet."}, status=503)
        serializer = PersonnelInput(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"detail": " ".join(str(error) for errors in serializer.errors.values() for error in errors)[:500]},
                status=400,
            )
        values = dict(serializer.validated_data)
        key = values.pop("idempotency_key")
        try:
            item, created = submit_form(tutor=request.user, key=key, values=values)
        except UploadConflict as exc:
            return Response({"detail": str(exc)}, status=409)
        except DjangoValidationError:
            return Response(
                {"detail": "Unable to validate the form. Check the details or contact the academy."}, status=400
            )
        except (OSError, DatabaseError, BotoCoreError, ClientError):
            return Response({"detail": "Unable to save the form now. Retry the same submission."}, status=503)
        return Response(summary(item), status=201 if created else 200)


class TutorPersonnelPDFView(PrivateTutorFormsAPIView):
    @extend_schema(responses={200: bytes})
    def get(self, request, form_id):
        item = get_object_or_404(TutorPersonnelForm, pk=form_id, tutor=request.user)
        try:
            return pdf_response(item)
        except (DjangoValidationError, OSError, BotoCoreError, ClientError):
            return Response({"detail": "The saved form is temporarily unavailable. Contact the academy."}, status=503)
