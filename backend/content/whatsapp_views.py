"""Opt-in management and Meta-signed delivery receipt handling."""
import hashlib
import hmac
import json
import os
import re

from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import SupabaseStudentAuthentication
from .whatsapp import WhatsAppDelivery, WhatsAppPreference


class PreferenceSerializer(serializers.Serializer):
    number = serializers.RegexField(r"^\+[1-9][0-9]{7,14}$", required=False)
    opted_in = serializers.BooleanField()


class PreferenceBaseView(APIView):
    permission_classes = (IsAuthenticated,)

    def owner(self, request):
        raise NotImplementedError

    def get(self, request):
        preference = WhatsAppPreference.objects.filter(**self.owner(request)).first()
        return Response({
            "number": preference.number if preference else "",
            "opted_in": bool(preference and preference.opted_in),
        })

    def post(self, request):
        serializer = PreferenceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        owner = self.owner(request)
        pref = WhatsAppPreference.objects.filter(**owner).first()
        if data["opted_in"]:
            number = data.get("number") or (pref.number if pref else None)
            if not number:
                return Response({"number": ["A valid WhatsApp number is required."]}, status=400)
            # Explicit affirmative request is the only route to consent.
            from django.utils import timezone
            pref, _ = WhatsAppPreference.objects.update_or_create(
                **owner, defaults={
                    "number": number,
                    "opted_in": True,
                    "consent_recorded_at": timezone.now(),
                }
            )
        elif pref:
            pref.opted_in = False
            pref.save(update_fields=["opted_in"])
        return Response({"opted_in": data["opted_in"]})


class StudentWhatsAppPreferenceView(PreferenceBaseView):
    authentication_classes = (SupabaseStudentAuthentication,)

    def owner(self, request):
        return {"student": request.user.student}


class TutorWhatsAppPreferenceView(PreferenceBaseView):
    authentication_classes = (SessionAuthentication,)

    def owner(self, request):
        if not request.user.is_active or not request.user.groups.filter(name__iexact="tutor").exists():
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied()
        return {"tutor": request.user}


@csrf_exempt
def meta_whatsapp_webhook(request):
    """Only Meta-signed POSTs may change delivery receipt status."""
    if request.method == "GET":
        verify = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "")
        if verify and request.GET.get("hub.mode") == "subscribe" and hmac.compare_digest(
            request.GET.get("hub.verify_token", ""), verify
        ):
            return HttpResponse(request.GET.get("hub.challenge", ""))
        return HttpResponse(status=403)
    if request.method != "POST":
        return HttpResponse(status=405)
    secret = os.getenv("WHATSAPP_APP_SECRET", "")
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not secret or not signature.startswith("sha256="):
        return HttpResponse(status=403)
    expected = hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature[7:], expected):
        return HttpResponse(status=403)
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return HttpResponse(status=400)
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            for receipt in change.get("value", {}).get("statuses", []):
                provider_id = receipt.get("id")
                if not provider_id:
                    continue
                state = receipt.get("status")
                if state in ("delivered", "read"):
                    WhatsAppDelivery.objects.filter(provider_id=provider_id).update(
                        receipt_status=state
                    )
                elif state == "sent":
                    WhatsAppDelivery.objects.filter(provider_id=provider_id).update(
                        receipt_status="sent"
                    )
                elif state == "failed":
                    WhatsAppDelivery.objects.filter(provider_id=provider_id).update(
                        status=WhatsAppDelivery.Status.FAILED, error_code="provider_failed",
                        receipt_status="failed"
                    )
                # 'sent' is not proof of device delivery. The original model
                # currently records API acceptance; receipts need separate fields
                # before persisting delivered/read without overwriting that state.
    return JsonResponse({"ok": True})
