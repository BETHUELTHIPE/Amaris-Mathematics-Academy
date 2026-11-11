"""Read-only sponsor workspace. Identity and ownership are enforced server-side."""

import csv
import io
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import SupabaseStudentAuthentication
from .sponsor_models import SponsorAccount, SponsorAllocation, SponsorContribution


class SupabaseSponsorAuthentication(BaseAuthentication):
    def authenticate(self, request):
        header = get_authorization_header(request).split()
        if not header:
            return None
        if len(header) != 2 or header[0].lower() != b"bearer":
            raise AuthenticationFailed("A verified sponsor session is required.")
        try:
            token = header[1].decode("ascii")
        except UnicodeDecodeError as exc:
            raise AuthenticationFailed("The sponsor session is invalid.") from exc
        payload = SupabaseStudentAuthentication()._validate_token(token)
        if not payload.get("email_confirmed_at") or not payload.get("id"):
            raise AuthenticationFailed("Verify your email before accessing the sponsor dashboard.")
        try:
            sponsor = SponsorAccount.objects.filter(supabase_user_id=payload["id"], is_active=True).first()
        except (ValueError, DjangoValidationError) as exc:
            raise AuthenticationFailed("The sponsor identity is invalid.") from exc
        if sponsor is None:
            raise PermissionDenied("Sponsor access has not been approved for this account.")
        return sponsor, {"provider": "supabase", "role": "sponsor"}

    def authenticate_header(self, request):
        return "Bearer"


class SponsorAPIView(APIView):
    authentication_classes = (SupabaseSponsorAuthentication,)
    permission_classes = (IsAuthenticated,)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        response["Vary"] = "Authorization"
        return response


class SponsorIdentitySerializer(serializers.Serializer):
    name = serializers.CharField()
    organisation = serializers.CharField(allow_blank=True)
    annual_target = serializers.CharField()


class SponsorSummarySerializer(serializers.Serializer):
    received = serializers.CharField()
    pledged = serializers.CharField()
    allocated = serializers.CharField()
    balance = serializers.CharField()
    students_supported = serializers.IntegerField()
    active_students = serializers.IntegerField()
    current_year_received = serializers.CharField()


class SponsorLearnerSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    learner_label = serializers.CharField()
    programme = serializers.CharField()
    programme_label = serializers.CharField()
    level = serializers.CharField()
    amount = serializers.CharField()
    status = serializers.CharField()
    starts_on = serializers.DateField()
    ends_on = serializers.DateField(allow_null=True)
    progress_percent = serializers.IntegerField(allow_null=True)
    progress_updated_at = serializers.DateTimeField(allow_null=True)


class SponsorContributionSerializer(serializers.Serializer):
    reference = serializers.CharField()
    amount = serializers.CharField()
    status = serializers.CharField()
    date = serializers.DateTimeField()
    description = serializers.CharField(allow_blank=True)


class SponsorMonthSerializer(serializers.Serializer):
    month = serializers.DateField()
    amount = serializers.CharField()


class SponsorProgrammeSerializer(serializers.Serializer):
    programme = serializers.CharField()
    amount = serializers.CharField()


class SponsorDashboardSerializer(serializers.Serializer):
    sponsor = SponsorIdentitySerializer()
    summary = SponsorSummarySerializer()
    currency = serializers.CharField()
    as_of = serializers.DateTimeField()
    year = serializers.IntegerField()
    monthly_contributions = SponsorMonthSerializer(many=True)
    programme_allocations = SponsorProgrammeSerializer(many=True)
    learners = SponsorLearnerSerializer(many=True)
    contributions = SponsorContributionSerializer(many=True)
    learners_total = serializers.IntegerField()
    contributions_total = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()


def _money(value):
    return f"{value or Decimal('0'):.2f}"


def _sum(queryset):
    return queryset.aggregate(total=Sum("amount"))["total"] or Decimal("0")


def _year(request):
    try:
        year = int(request.query_params.get("year", timezone.localdate().year))
    except (TypeError, ValueError) as exc:
        raise serializers.ValidationError({"year": "Choose a valid reporting year."}) from exc
    if not 2020 <= year <= timezone.localdate().year:
        raise serializers.ValidationError({"year": "Choose a year from 2020 through the current year."})
    return year


def _learner_data(allocation):
    can_share = (
        allocation.share_progress
        and allocation.progress_consented_at is not None
        and allocation.enrollment_id is not None
        and allocation.enrollment.student_id == allocation.student_id
    )
    return {
        "id": allocation.id,
        "learner_label": allocation.learner_label,
        "programme": allocation.programme,
        "programme_label": allocation.get_programme_display(),
        "level": allocation.level,
        "amount": _money(allocation.amount),
        "status": allocation.status,
        "starts_on": allocation.starts_on,
        "ends_on": allocation.ends_on,
        "progress_percent": allocation.enrollment.progress_percent if can_share else None,
        "progress_updated_at": allocation.enrollment.progress_updated_at if can_share else None,
    }


class SponsorDashboardView(SponsorAPIView):
    @extend_schema(
        responses={200: SponsorDashboardSerializer},
        parameters=[OpenApiParameter("year", int), OpenApiParameter("page", int)],
    )
    def get(self, request):
        year = _year(request)
        try:
            page = int(request.query_params.get("page", 1))
        except (TypeError, ValueError) as exc:
            raise serializers.ValidationError({"page": "Choose a valid page."}) from exc
        if not 1 <= page <= 100000:
            raise serializers.ValidationError({"page": "Choose a valid page."})
        page_size = 20
        offset = (page - 1) * page_size
        contributions = SponsorContribution.objects.filter(sponsor=request.user)
        received = contributions.filter(status=SponsorContribution.Status.RECEIVED)
        allocations = SponsorAllocation.objects.filter(sponsor=request.user)
        committed = allocations.filter(status__in=("active", "completed"))
        year_received = received.filter(received_at__year=year)
        monthly = {
            row["month"].month: row["amount"]
            for row in year_received.annotate(month=TruncMonth("received_at"))
            .values("month")
            .annotate(amount=Sum("amount"))
            .order_by("month")
        }
        total_received, total_allocated = _sum(received), _sum(committed)
        year_contributions = contributions.filter(
            Q(received_at__year=year) | Q(received_at__isnull=True, created_at__year=year)
        )
        return Response(
            {
                "sponsor": {
                    "name": request.user.name,
                    "organisation": request.user.organisation,
                    "annual_target": _money(request.user.annual_target),
                },
                "summary": {
                    "received": _money(total_received),
                    "pledged": _money(_sum(contributions.filter(status="pledged"))),
                    "allocated": _money(total_allocated),
                    "balance": _money(total_received - total_allocated),
                    "students_supported": committed.values("student_id").distinct().count(),
                    "active_students": committed.filter(status="active").values("student_id").distinct().count(),
                    "current_year_received": _money(_sum(received.filter(received_at__year=timezone.localdate().year))),
                },
                "currency": "ZAR",
                "as_of": timezone.now(),
                "year": year,
                "monthly_contributions": [
                    {"month": date(year, month, 1), "amount": _money(monthly.get(month))} for month in range(1, 13)
                ],
                "programme_allocations": [
                    {
                        "programme": dict(SponsorAllocation._meta.get_field("programme").choices).get(
                            row["programme"], row["programme"]
                        ),
                        "amount": _money(row["amount"]),
                    }
                    for row in committed.values("programme").annotate(amount=Sum("amount")).order_by("programme")
                ],
                "learners": [
                    _learner_data(item)
                    for item in allocations.select_related("enrollment")[offset : offset + page_size]
                ],
                "contributions": [
                    {
                        "reference": item.reference,
                        "amount": _money(item.amount),
                        "status": item.status,
                        "date": item.received_at or item.created_at,
                        "description": item.description,
                    }
                    for item in year_contributions[offset : offset + page_size]
                ],
                "learners_total": allocations.count(),
                "contributions_total": year_contributions.count(),
                "page": page,
                "page_size": page_size,
            }
        )


def _csv_cell(value):
    value = str(value)
    # Prevent spreadsheet formulas when a contribution reference is exported.
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else value


class SponsorStatementView(SponsorAPIView):
    @extend_schema(responses={(200, "text/csv"): bytes}, parameters=[OpenApiParameter("year", int)])
    def get(self, request):
        year = _year(request)
        records = SponsorContribution.objects.filter(sponsor=request.user)
        records = records.filter(Q(received_at__year=year) | Q(received_at__isnull=True, created_at__year=year))
        # Keep exports bounded; never silently truncate a financial statement.
        if records.count() > 10000:
            raise serializers.ValidationError("This statement is too large. Contact Amaris for a complete export.")
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Reference", "Date (SAST)", "Description", "Status", "Amount", "Currency"])
        for item in records.iterator(chunk_size=500):
            writer.writerow(
                [
                    _csv_cell(item.reference),
                    timezone.localtime(item.received_at or item.created_at).isoformat(),
                    _csv_cell(item.description),
                    item.get_status_display(),
                    _money(item.amount),
                    "ZAR",
                ]
            )
        response = HttpResponse("\ufeff" + output.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="amaris-sponsor-statement-{year}.csv"'
        return response
