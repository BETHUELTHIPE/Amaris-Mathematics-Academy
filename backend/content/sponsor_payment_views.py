import json

from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from .services.payments import PaymentSecurityError
from .services.sponsor_payments import (
    SponsorGatewayUnavailable,
    create_checkout,
    resume_checkout,
    valid_paystack_signature,
    verify_paystack,
)
from .sponsor_models import SponsorContribution
from .sponsor_views import SponsorAPIView


class SponsorPaymentThrottle(UserRateThrottle):
    scope = "sponsor_payments"
    rate = "30/hour"


class SponsorCheckoutRequestSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=9, decimal_places=2, min_value=10, max_value=1000000)
    provider = serializers.ChoiceField(choices=("payfast", "paystack"))
    idempotency_key = serializers.UUIDField()


class SponsorCheckoutResponseSerializer(serializers.Serializer):
    reference = serializers.CharField()
    provider = serializers.CharField()
    mode = serializers.CharField()
    amount = serializers.CharField()
    currency = serializers.CharField()
    gateway_url = serializers.URLField()
    fields = serializers.DictField(child=serializers.CharField())


class SponsorPaymentStatusSerializer(serializers.Serializer):
    reference = serializers.CharField()
    provider = serializers.CharField()
    mode = serializers.CharField()
    amount = serializers.CharField()
    currency = serializers.CharField()
    status = serializers.CharField()
    gateway_verified = serializers.BooleanField()
    checkout = serializers.DictField(allow_null=True)


def payment_status(contribution):
    return {
        "reference": contribution.reference,
        "provider": contribution.provider,
        "mode": contribution.payment_mode,
        "amount": f"{contribution.amount:.2f}",
        "currency": "ZAR",
        "status": contribution.status,
        "gateway_verified": contribution.gateway_verified_at is not None,
        "checkout": resume_checkout(contribution),
    }


class SponsorCheckoutView(SponsorAPIView):
    throttle_classes = (SponsorPaymentThrottle,)

    @extend_schema(request=SponsorCheckoutRequestSerializer, responses={201: SponsorCheckoutResponseSerializer})
    def post(self, request):
        serializer = SponsorCheckoutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializers.EmailField().run_validation((request.auth or {}).get("email", ""))
        try:
            session = create_checkout(sponsor=request.user, email=email, **serializer.validated_data)
        except PaymentSecurityError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        except SponsorGatewayUnavailable:
            return Response(
                {
                    "detail": (
                        "We could not open this checkout. "
                        "Check your contribution history before starting another payment."
                    )
                },
                status=503,
            )
        return Response(session, status=201)


class SponsorPaymentStatusView(SponsorAPIView):
    @extend_schema(responses={200: SponsorPaymentStatusSerializer})
    def get(self, request, reference):
        contribution = get_object_or_404(SponsorContribution, sponsor=request.user, reference=reference)
        return Response(payment_status(contribution))


class SponsorPaymentVerifyView(SponsorAPIView):
    throttle_classes = (SponsorPaymentThrottle,)

    @extend_schema(request=None, responses={200: SponsorPaymentStatusSerializer})
    def post(self, request, reference):
        contribution = get_object_or_404(SponsorContribution, sponsor=request.user, reference=reference)
        if contribution.provider != "paystack":
            raise serializers.ValidationError(
                "PayFast confirmation is received automatically. Check payment status shortly."
            )
        try:
            verify_paystack(reference)
        except (PaymentSecurityError, IntegrityError):
            return Response(
                {"detail": "The gateway has not confirmed this contribution. Please check again shortly."}, status=409
            )
        except SponsorGatewayUnavailable:
            return Response({"detail": "Gateway confirmation is temporarily unavailable."}, status=503)
        contribution.refresh_from_db()
        return Response(payment_status(contribution))


class SponsorPaystackWebhookView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = ()

    @extend_schema(request=dict, responses={200: dict}, auth=[])
    def post(self, request):
        raw = request.body
        if len(raw) > 65536:
            return Response({"detail": "Invalid notification."}, status=400)
        try:
            valid = valid_paystack_signature(raw, request.headers)
        except SponsorGatewayUnavailable:
            return Response({"detail": "Verification is temporarily unavailable."}, status=503)
        if not valid:
            return Response({"detail": "Invalid payment signature."}, status=401)
        try:
            event = json.loads(raw)
            if not isinstance(event, dict):
                raise ValueError
            data = event.get("data")
            if event.get("event") != "charge.success":
                return Response({"status": "ignored"})
            if not isinstance(data, dict):
                raise ValueError
            reference = data.get("reference")
            if not isinstance(reference, str) or not reference.startswith("SC-") or len(reference) > 100:
                return Response({"status": "ignored"})
            # Own contribution records only. The signed event is still verified
            # independently against Paystack before any funds are recorded.
            verify_paystack(reference)
        except (ValueError, SponsorContribution.DoesNotExist, PaymentSecurityError, IntegrityError):
            return Response({"detail": "Sponsor payment verification failed."}, status=400)
        except SponsorGatewayUnavailable:
            return Response({"detail": "Gateway confirmation is temporarily unavailable."}, status=503)
        return Response({"status": "processed"})
