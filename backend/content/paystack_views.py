"""Paystack webhook — signed raw bytes plus mandatory API verification."""
import hashlib
import hmac
import json
import logging
import os
import re
import time

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .services.payments import PaymentSecurityError
from .services.paystack import verify_and_settle

logger = logging.getLogger(__name__)


@csrf_exempt
def paystack_webhook(request):
    if request.method != "POST":
        return HttpResponse(status=405)
    modern = request.headers.get("Paystack-Signature", "")
    legacy = request.headers.get("x-paystack-signature", "")
    if modern:
        secret = os.getenv("PAYSTACK_WEBHOOK_SECRET", "")
        pieces = [part.strip() for part in modern.split(",")]
        timestamp = [part[2:] for part in pieces if part.startswith("t=")]
        signed = [part[3:].split(":", 1) for part in pieces if part.startswith("v1=") and ":" in part]
        if (
            not secret.startswith("whsec_")
            or len(timestamp) != 1
            or not timestamp[0].isdigit()
            or abs(time.time() - int(timestamp[0])) > 300
        ):
            return HttpResponse(status=403)
        expected = hmac.new(secret.encode(), timestamp[0].encode() + b"." + request.body, hashlib.sha512).hexdigest()
        if not any(re.fullmatch(r"[0-9a-f]{128}", value) and hmac.compare_digest(value, expected) for _, value in signed):
            return HttpResponse(status=403)
    else:
        secret = os.getenv("PAYSTACK_SECRET_KEY", "")
        if not secret or not re.fullmatch(r"[0-9a-f]{128}", legacy):
            return HttpResponse(status=403)
        expected = hmac.new(secret.encode(), request.body, hashlib.sha512).hexdigest()
        if not hmac.compare_digest(legacy, expected):
            return HttpResponse(status=403)
    try:
        event = json.loads(request.body)
    except (UnicodeDecodeError, ValueError):
        return HttpResponse(status=400)
    if event.get("event") != "charge.success":
        return JsonResponse({"status": "ignored"})
    reference = str(event.get("data", {}).get("reference", "")).strip()
    if not reference or not reference.startswith(("LCB-", "PS-")):
        return HttpResponse(status=400)
    try:
        result = verify_and_settle(reference)
    except PaymentSecurityError as exc:
        logger.warning("Paystack verification rejected: %s", type(exc).__name__)
        return HttpResponse(status=503)
    except Exception:
        logger.exception("Paystack settlement failed")
        return HttpResponse(status=503)
    return JsonResponse({"status": result})
