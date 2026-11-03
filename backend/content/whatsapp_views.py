"""Self-service WhatsApp consent and signed Meta webhook processing."""
import hashlib
import hmac
import json
import os
import re

from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import SupabaseStudentAuthentication
from .whatsapp import WhatsAppDelivery, WhatsAppPreference


class PreferenceSerializer(serializers.Serializer):
    number = serializers.RegexField(
        r"^\+[1-9][0-9]{7,14}$", required=False, allow_blank=True
    )
    opted_in = serializers.BooleanField()


class PreferenceBaseView(APIView):
    permission_classes = (IsAuthenticated,)

    def owner(self, request):
        raise NotImplementedError

    def get(self, request):
        preference = WhatsAppPreference.objects.filter(**self.owner(request)).first()
        return Response(
            {
                "number": preference.number if preference else "",
                "opted_in": bool(preference and preference.opted_in),
            }
        )

    def post(self, request):
        serializer = PreferenceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        owner = self.owner(request)
        pref = WhatsAppPreference.objects.filter(**owner).first()
        if values["opted_in"]:
            number = values.get("number", "")
            if not number:
                return Response(
                    {"number": ["A valid WhatsApp number is required."]}, status=400
                )
            pref, _created = WhatsAppPreference.objects.update_or_create(
                **owner,
                defaults={
                    "number": number,
                    "opted_in": True,
                    "consent_recorded_at": timezone.now(),
                    "consent_source": (
                        "student_dashboard" if owner.get("student") else "tutor_account"
                    ),
                },
            )
            pref.full_clean()
        elif pref:
            pref.opted_in = False
            pref.save(update_fields=["opted_in"])
        # Opt-out only affects WhatsApp. Booking confirmation emails continue.
        return Response({"opted_in": bool(values["opted_in"])})


class StudentWhatsAppPreferenceView(PreferenceBaseView):
    authentication_classes = (SupabaseStudentAuthentication,)

    def owner(self, request):
        return {"student": request.user.student}


class TutorWhatsAppPreferenceView(PreferenceBaseView):
    authentication_classes = (SessionAuthentication,)

    def owner(self, request):
        if (
            not request.user.is_active
            or not request.user.groups.filter(name__iexact="tutor").exists()
        ):
            raise PermissionDenied("Tutor access is required.")
        return {"tutor": request.user}


def _apply_receipt(receipt):
    provider_id = receipt.get("id")
    state = receipt.get("status")
    if not isinstance(provider_id, str):
        return
    deliveries = WhatsAppDelivery.objects.filter(provider_id=provider_id)
    # Out-of-order/duplicated webhooks must not downgrade a read receipt.
    if state == "read":
        deliveries.exclude(receipt_status="read").update(receipt_status="read")
    elif state == "delivered":
        deliveries.filter(receipt_status__in=["", "sent"]).update(
            receipt_status="delivered"
        )
    elif state == "sent":
        deliveries.filter(receipt_status="").update(receipt_status="sent")
    elif state == "failed":
        deliveries.exclude(receipt_status__in=["delivered", "read"]).update(
            receipt_status="failed",
            status=WhatsAppDelivery.Status.FAILED,
            error_code="provider_failed",
        )


def _apply_inbound(message):
    # Meta sends the sender in wa_id format (digits, without '+').
    sender = str(message.get("from", "")).lstrip("+")
    text = message.get("text")
    if not sender.isdecimal() or not isinstance(text, dict):
        return
    body = text.get("body", "")
    if not isinstance(body, str) or body.strip().upper() not in {
        "STOP", "UNSUBSCRIBE", "CANCEL", "QUIT", "END"
    }:
        return
    number = f"+{sender}"
    if not re.fullmatch(r"\+[1-9][0-9]{7,14}", number):
        return
    prefs = WhatsAppPreference.objects.filter(number=number, opted_in=True)
    ids = list(prefs.values_list("pk", flat=True))
    if not ids:
        return
    WhatsAppPreference.objects.filter(pk__in=ids).update(opted_in=False)
    WhatsAppDelivery.objects.filter(
        preference_id__in=ids,
        status__in=[WhatsAppDelivery.Status.PENDING, WhatsAppDelivery.Status.RETRY],
    ).update(status=WhatsAppDelivery.Status.SKIPPED, error_code="opted_out")
    # START is intentionally not a re-subscription; the person must opt in
    # explicitly through their authenticated account again.


@csrf_exempt
def meta_whatsapp_webhook(request):
    """Verify Meta signature before processing messages, STOP, or receipts."""
    if request.method == "GET":
        token = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "")
        candidate = request.GET.get("hub.verify_token", "")
        if (
            token
            and request.GET.get("hub.mode") == "subscribe"
            and hmac.compare_digest(candidate, token)
        ):
            return HttpResponse(request.GET.get("hub.challenge", ""))
        return HttpResponse(status=403)
    if request.method != "POST":
        return HttpResponse(status=405)
    if len(request.body) > 512 * 1024:
        return HttpResponse(status=413)
    secret = os.getenv("WHATSAPP_APP_SECRET", "")
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not secret or not signature.startswith("sha256="):
        return HttpResponse(status=403)
    expected = hmac.new(
        secret.encode("utf-8"), request.body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature[7:], expected):
        return HttpResponse(status=403)
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return HttpResponse(status=400)
    if not isinstance(data, dict):
        return HttpResponse(status=400)
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    for entry in data.get("entry", []):
        if not isinstance(entry, dict):
            continue
        for change in entry.get("changes", []):
            if not isinstance(change, dict):
                continue
            value = change.get("value", {})
            if not isinstance(value, dict):
                continue
            # An app may contain several sender numbers. Reject cross-number
            # events when configured, even if the app signature is valid.
            if phone_id and value.get("metadata", {}).get("phone_number_id") != phone_id:
                continue
            for receipt in value.get("statuses", []):
                if isinstance(receipt, dict):
                    _apply_receipt(receipt)
            for message in value.get("messages", []):
                if isinstance(message, dict):
                    _apply_inbound(message)
    return JsonResponse({"ok": True})
