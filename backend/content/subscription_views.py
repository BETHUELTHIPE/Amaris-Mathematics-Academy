from datetime import datetime

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response

from .services.payments import PaymentSecurityError
from .services.subscriptions import create_subscription_checkout, subscription_invoice
from .student_views import StudentAPIView
from .subscription_models import CurriculumSubscription


class SubscriptionInput(serializers.Serializer):
    curriculum = serializers.ChoiceField(choices=CurriculumSubscription.Curriculum.choices)
    months = serializers.ChoiceField(choices=[4, 8])
    idempotency_key = serializers.RegexField(r"^[A-Za-z0-9_-]{8,64}$")


class SubscriptionOutput(serializers.ModelSerializer):
    curriculum_label = serializers.CharField(source="get_curriculum_display")
    active = serializers.SerializerMethodField()
    report_ready = serializers.SerializerMethodField()
    report_emailed_at = serializers.SerializerMethodField()

    class Meta:
        model = CurriculumSubscription
        fields = (
            "reference",
            "curriculum",
            "curriculum_label",
            "months",
            "amount",
            "currency",
            "status",
            "gateway_mode",
            "starts_at",
            "ends_at",
            "active",
            "report_ready",
            "report_emailed_at",
        )

    def get_report_ready(self, obj) -> bool:
        from .subscription_report_models import SubscriptionReport

        try:
            return bool(obj.final_report.pdf_storage_path)
        except SubscriptionReport.DoesNotExist:
            return False

    def get_report_emailed_at(self, obj) -> datetime | None:
        from .subscription_report_models import SubscriptionReport

        try:
            return obj.final_report.emailed_at
        except SubscriptionReport.DoesNotExist:
            return None

    def get_active(self, obj) -> bool:
        from .services.payments import _payfast_mode

        return bool(
            obj.status == "paid"
            and obj.gateway_verified_at
            and obj.gateway_mode == _payfast_mode()
            and obj.starts_at
            and obj.ends_at
            and obj.starts_at <= timezone.now() < obj.ends_at
        )


class SubscriptionListView(StudentAPIView):
    @extend_schema(responses=SubscriptionOutput(many=True))
    def get(self, request):
        return Response(
            SubscriptionOutput(
                CurriculumSubscription.objects.filter(student=self.student).select_related("final_report")[:100],
                many=True,
            ).data
        )


class SubscriptionCheckoutView(StudentAPIView):
    @extend_schema(request=SubscriptionInput, responses=dict)
    def post(self, request):
        data = SubscriptionInput(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            item, url, fields = create_subscription_checkout(student=self.student, **data.validated_data)
        except PaymentSecurityError as exc:
            return Response({"detail": str(exc)}, status=409)
        return Response(
            {"subscription": SubscriptionOutput(item).data, "gateway_url": url, "fields": fields}, status=201
        )


class SubscriptionStatusView(StudentAPIView):
    @extend_schema(responses=SubscriptionOutput)
    def get(self, request, reference):
        return Response(
            SubscriptionOutput(
                get_object_or_404(CurriculumSubscription, student=self.student, reference=reference)
            ).data
        )


class SubscriptionInvoiceView(StudentAPIView):
    @extend_schema(responses={(200, "application/pdf"): bytes})
    def get(self, request, reference):
        item = get_object_or_404(
            CurriculumSubscription.objects.select_related("student"), student=self.student, reference=reference
        )
        try:
            document = subscription_invoice(item)
        except PaymentSecurityError as exc:
            return Response({"detail": str(exc)}, status=409)
        except OSError:
            return Response({"detail": "Invoice temporarily unavailable."}, status=503)
        response = FileResponse(document, as_attachment=True, filename=f"INV-{item.reference}.pdf")
        response["Cache-Control"] = "private, no-store"
        return response
