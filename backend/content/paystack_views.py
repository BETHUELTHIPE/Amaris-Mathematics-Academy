from __future__ import annotations

import json
import logging

from django.db import DatabaseError
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .services import paystack
from .services.live_classes import process_paystack_live_class_payment
from .services.payments import PaymentSecurityError

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def paystack_webhook(request):
    if not paystack.valid_webhook(
        request.body,
        request.headers.get("Paystack-Signature", ""),
        request.headers.get("X-Paystack-Signature", ""),
    ):
        return HttpResponse(status=403)
    try:
        event = json.loads(request.body)
    except (UnicodeDecodeError, ValueError):
        return HttpResponse(status=400)
    if not isinstance(event, dict):
        return HttpResponse(status=400)
    if event.get("event") != "charge.success":
        return JsonResponse({"status": "ignored"})
    data = event.get("data")
    reference = data.get("reference") if isinstance(data, dict) else None
    if not isinstance(reference, str):
        return HttpResponse(status=400)
    if not paystack.BOOKING_REFERENCE.fullmatch(reference):
        return JsonResponse({"status": "ignored"})
    try:
        result = process_paystack_live_class_payment(reference)
    except (paystack.PaystackUnavailable, DatabaseError):
        logger.warning("Paystack live-class settlement is temporarily unavailable.")
        return HttpResponse(status=503)
    except PaymentSecurityError:
        logger.warning("Paystack live-class settlement failed verification.")
        return HttpResponse(status=400)
    return JsonResponse({"status": result})
