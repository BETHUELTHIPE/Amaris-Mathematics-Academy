from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DatabaseError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from content.services.tutor_contracts import (
    ContractInputError,
    archived_contract_pdf,
    offer_summary,
    submit_contract,
)
from content.services.tutor_video_uploads import UploadConflict
from content.tutor_contract_models import TutorEmploymentContract
from content.tutor_views import TutorOnlyAPIView


class ContractInput(serializers.Serializer):
    idempotency_key = serializers.RegexField(r"^[A-Za-z0-9_-]{8,64}$")
    residential_address = serializers.CharField(min_length=10, max_length=500)
    contact_phone = serializers.RegexField(r"^\+?[0-9 ()-]{7,25}$")
    preferred_start_date = serializers.DateField()
    ordinary_work_days = serializers.ListField(
        child=serializers.ChoiceField(
            choices=[
                (day, day)
                for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
            ]
        ),
        min_length=1,
        max_length=7,
    )
    maximum_weekly_hours = serializers.IntegerField(min_value=1, max_value=45)
    signature_name = serializers.CharField(min_length=2, max_length=150)
    accept_employment_terms = serializers.BooleanField()
    accept_privacy_notice = serializers.BooleanField()
    accept_safeguarding_duties = serializers.BooleanField()
    consent_electronic_signature = serializers.BooleanField()

    def validate(self, data):
        confirmations = (
            "accept_employment_terms",
            "accept_privacy_notice",
            "accept_safeguarding_duties",
            "consent_electronic_signature",
        )
        if not all(data[name] is True for name in confirmations):
            raise serializers.ValidationError("Confirm every declaration before signing.")
        if len(data["ordinary_work_days"]) != len(set(data["ordinary_work_days"])):
            raise serializers.ValidationError("Choose each ordinary work day only once.")
        return data


class ContractThrottle(UserRateThrottle):
    scope = "tutor-contracts"
    rate = "5/hour"


def summary(item):
    return {
        "id": str(item.pk),
        "created_at": item.created_at,
        "status": item.status,
        "status_label": item.get_status_display(),
        "review_notes": item.review_notes,
        "reviewed_at": item.reviewed_at,
        "effective_date": item.effective_date,
        "terms_version": item.terms_version,
        "details": item.payload,
        "service_terms": item.service_terms,
        "pdf_path": f"/api/tutor/contracts/{item.pk}/pdf",
        "executed": bool(item.executed_pdf),
    }


def pdf_response(item):
    response = HttpResponse(archived_contract_pdf(item), content_type="application/pdf")
    suffix = "executed" if item.status == item.Status.ACCEPTED and item.executed_pdf else "tutor-signed"
    response["Content-Disposition"] = f'attachment; filename="amaris-tutor-employment-{suffix}-{item.pk}.pdf"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


class PrivateContractAPIView(TutorOnlyAPIView):
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        response["Vary"] = "Authorization"
        return response


class TutorEmploymentContractsView(PrivateContractAPIView):
    parser_classes = (JSONParser,)

    def get_throttles(self):
        return [ContractThrottle()] if self.request.method == "POST" else [UserRateThrottle()]

    @extend_schema(responses=dict)
    def get(self, request):
        rows = TutorEmploymentContract.objects.filter(tutor=request.user)[:10]
        return Response({"offer": offer_summary(request.user), "results": [summary(item) for item in rows]})

    @extend_schema(request=ContractInput, responses=dict)
    def post(self, request):
        if not settings.TUTOR_PERSONNEL_FORMS_ENABLED:
            return Response({"detail": "Tutor employment contracts are not available yet."}, status=503)
        serializer = ContractInput(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"detail": " ".join(str(error) for errors in serializer.errors.values() for error in errors)[:500]},
                status=400,
            )
        values = dict(serializer.validated_data)
        key = values.pop("idempotency_key")
        try:
            item, created = submit_contract(tutor=request.user, key=key, values=values)
        except UploadConflict as exc:
            return Response({"detail": str(exc)}, status=409)
        except ContractInputError as exc:
            return Response({"detail": str(exc)}, status=409)
        except DjangoValidationError:
            return Response(
                {"detail": "Unable to validate the contract. Check the details or contact the academy."},
                status=400,
            )
        except (OSError, DatabaseError, BotoCoreError, ClientError):
            return Response({"detail": "Unable to save the contract now. Retry the same submission."}, status=503)
        return Response(summary(item), status=201 if created else 200)


class TutorEmploymentContractPDFView(PrivateContractAPIView):
    @extend_schema(responses={200: bytes})
    def get(self, request, contract_id):
        item = get_object_or_404(TutorEmploymentContract, pk=contract_id, tutor=request.user)
        try:
            return pdf_response(item)
        except (DjangoValidationError, OSError, BotoCoreError, ClientError):
            return Response(
                {"detail": "The saved contract is temporarily unavailable. Contact the academy."}, status=503
            )
