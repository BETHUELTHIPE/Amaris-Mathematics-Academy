from __future__ import annotations

import ipaddress
import logging
import os

from django.db import InterfaceError, OperationalError
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import ErrorDetailSerializer, PayFastITNRequestSerializer, PayFastITNStatusSerializer
from .services.live_classes import process_live_class_notification
from .services.payments import HttpPayFastVerificationGateway, process_payfast_notification
from .services.video_requests import process_video_request_notification

DEFAULT_PAYFAST_NETWORKS = (
    "197.97.145.144/28",
    "41.74.179.192/27",
    "102.216.36.0/28",
    "102.216.36.128/28",
    "144.126.193.139/32",
)

logger = logging.getLogger("amaris.payfast")


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

    @extend_schema(
        request=PayFastITNRequestSerializer,
        responses={
            200: PayFastITNStatusSerializer,
            400: ErrorDetailSerializer,
            403: ErrorDetailSerializer,
            503: ErrorDetailSerializer,
        },
        auth=[],
    )
    def post(self, request):
        # Deliberately omit IPs, identifiers, payloads and signatures. The ASGI
        # access log is disabled for privacy, so these outcomes are the safe
        # way to distinguish missing delivery from a rejected notification.
        logger.info("payfast_itn received")
        remote_ip = _request_ip(request)
        try:
            source = ipaddress.ip_address(remote_ip)
        except ValueError:
            logger.warning("payfast_itn rejected reason=invalid_source")
            return Response({"detail": "Invalid payment notification source."}, status=403)

        if not any(source in network for network in _allowed_networks()):
            logger.warning("payfast_itn rejected reason=untrusted_source")
            return Response({"detail": "Payment notification source is not trusted."}, status=403)

        payload = {str(key): str(value) for key, value in request.data.items()}
        gateway = HttpPayFastVerificationGateway()
        local_reference = str(payload.get("m_payment_id", ""))
        try:
            if local_reference.startswith("LCB-"):
                result = process_live_class_notification(payload, gateway=gateway)
            elif local_reference.startswith("VRQ-"):
                result = process_video_request_notification(payload, gateway=gateway)
            else:
                result = process_payfast_notification(payload, gateway=gateway)
        except (OperationalError, InterfaceError):
            # Never acknowledge an uncommitted payment. Ask PayFast to retry,
            # without logging database messages that can contain credentials/PII.
            logger.warning("payfast_itn retryable reason=database_unavailable")
            return Response({"detail": "database_unavailable"}, status=503)
        if result.accepted:
            logger.info("payfast_itn accepted")
            return Response({"status": result.payment_status}, status=200)
        if result.retryable:
            logger.warning("payfast_itn retryable reason=%s", result.reason)
            return Response({"detail": result.reason}, status=503)
        logger.warning("payfast_itn rejected reason=%s", result.reason)
        return Response({"detail": result.reason}, status=400)
