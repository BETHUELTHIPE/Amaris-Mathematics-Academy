from __future__ import annotations

from decimal import Decimal

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .donation_models import DonationContribution
from .services.donations import create_donation_checkout, donations_available
from .services.payments import PaymentSecurityError, _payfast_mode


class DonationCheckoutSerializer(serializers.Serializer):
    donor_name = serializers.CharField(max_length=100, min_length=2, trim_whitespace=True)
    donor_email = serializers.EmailField()
    amount = serializers.DecimalField(
        max_digits=9, decimal_places=2, min_value=Decimal("20.00"), max_value=Decimal("100000.00")
    )
    purpose = serializers.ChoiceField(choices=DonationContribution.Purpose.choices)
    idempotency_key = serializers.RegexField(r"^[A-Za-z0-9_-]{12,64}$")
    consent = serializers.BooleanField()

    def validate_consent(self, value):
        if not value:
            raise serializers.ValidationError("You must confirm the contribution terms.")
        return value


class DonationAvailabilityView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(responses={200: dict}, auth=[])
    def get(self, request):
        ready = donations_available()
        # Do not advertise real-money payments in sandbox.
        live = _payfast_mode() == "live"
        return Response(
            {"available": ready and live, "test_mode": ready and not live, "currency": "ZAR", "minimum": "20.00"},
            headers={"Cache-Control": "no-store"},
        )


class DonationCheckoutView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "donations"

    @extend_schema(request=DonationCheckoutSerializer, responses={201: dict}, auth=[])
    def post(self, request):
        serializer = DonationCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        try:
            checkout = create_donation_checkout(
                name=values["donor_name"],
                email=values["donor_email"],
                amount=values["amount"],
                purpose=values["purpose"],
                idempotency_key=values["idempotency_key"],
            )
        except PaymentSecurityError as exc:
            return Response({"detail": str(exc)}, status=503 if "not yet enabled" in str(exc) else 400)
        return Response(
            {"payment_reference": checkout.reference, "gateway_url": checkout.gateway_url, "fields": checkout.fields},
            status=status.HTTP_201_CREATED,
            headers={"Cache-Control": "no-store"},
        )


class DonationStatusView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "donation_status"

    @extend_schema(responses={200: dict}, auth=[])
    def get(self, request, reference: str):
        contribution = get_object_or_404(
            DonationContribution.objects.only("reference", "status", "amount", "currency", "paid_at"),
            reference=reference,
        )
        # Reference is a random, unguessable key; never return donor PII.
        return Response(
            {
                "payment_reference": contribution.reference,
                "status": contribution.status,
                "amount": f"{contribution.amount:.2f}",
                "currency": contribution.currency,
                "verified_at": contribution.paid_at,
            },
            headers={"Cache-Control": "private, no-store"},
        )
