from __future__ import annotations

import ipaddress
import os

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .services.payments import HttpPayFastVerificationGateway, process_payfast_notification

DEFAULT_PAYFAST_NETWORKS = (
    "197.97.145.144/28",
    "41.74.179.192/27",
    "102.216.36.0/28",
    "102.216.36.128/28",
    "144.126.193.139/32",
)


def _allowed_networks():
    configured = os.getenv("PAYFAST_ALLOWED_NETWORKS", "").strip()
    values = (
        [item.strip() for item in configured.split(",") if item.strip()]
        if configured
        else list(DEFAULT_PAYFAST_NETWORKS)
    )
    return tuple(ipaddress.ip_network(value, strict=False) for value in values)


def _request_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return str(request.META.get("REMOTE_ADDR", "")).strip()


class PayFastITNView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def post(self, request):
        remote_ip = _request_ip(request)
        try:
            source = ipaddress.ip_address(remote_ip)
        except ValueError:
            return Response({"detail": "Invalid payment notification source."}, status=403)

        if not any(source in network for network in _allowed_networks()):
            return Response({"detail": "Payment notification source is not trusted."}, status=403)

        payload = {str(key): str(value) for key, value in request.data.items()}
        result = process_payfast_notification(
            payload,
            gateway=HttpPayFastVerificationGateway(),
        )
        if result.accepted:
            return Response({"status": result.payment_status}, status=200)
        if result.retryable:
            return Response({"detail": result.reason}, status=503)
        return Response({"detail": result.reason}, status=400)
