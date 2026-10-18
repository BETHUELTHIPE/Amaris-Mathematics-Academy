"""Verified Supabase tutors manage only their own live-class availability.

Tutor membership is approved in Django's Tutors group. No student endpoint,
public session, Supabase role claim or browser-supplied tutor ID grants access.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import SupabaseStudentAuthentication
from .models import LIVE_CLASS_MAX_HOURS, LiveClassBooking, TutorAvailabilitySlot
from .services.live_classes import LIVE_CLASS_PRICE, price_for_live_class_slot

TUTOR_GROUP = "Tutors"
RESERVED_STATUSES = (
    LiveClassBooking.Status.PENDING_PAYMENT,
    LiveClassBooking.Status.CONFIRMED,
    LiveClassBooking.Status.PAYMENT_REVIEW,
    LiveClassBooking.Status.COMPLETED,
)


class SupabaseTutorAuthentication(BaseAuthentication):
    """Reuse authoritative Supabase Auth validation without creating student profiles."""

    def authenticate(self, request):
        header = get_authorization_header(request).split()
        if not header:
            return None
        if len(header) != 2 or header[0].lower() != b"bearer":
            raise AuthenticationFailed("A verified Supabase session is required.")
        try:
            token = header[1].decode("ascii")
        except UnicodeDecodeError as exc:
            raise AuthenticationFailed("Invalid tutor session.") from exc

        # Deliberately do not support synthetic acceptance identities for tutors.
        payload = SupabaseStudentAuthentication()._validate_token(token)
        email = str(payload.get("email") or "").strip().lower()
        if not payload.get("id") or not email or not payload.get("email_confirmed_at"):
            raise AuthenticationFailed("A verified email address is required.")

        users = list(
            get_user_model()
            .objects.filter(email__iexact=email, is_active=True, groups__name=TUTOR_GROUP)
            .distinct()[:2]
        )
        if len(users) != 1:
            raise AuthenticationFailed("Tutor access has not been approved for this account.")
        return users[0], {"provider": "supabase", "role": "tutor"}

    def authenticate_header(self, request):
        return "Bearer"


class TutorOnlyAPIView(APIView):
    authentication_classes = (SupabaseTutorAuthentication,)
    permission_classes = (IsAuthenticated,)


class TutorSlotWriteSerializer(serializers.Serializer):
    programme = serializers.ChoiceField(choices=TutorAvailabilitySlot.Programme.choices)
    subject = serializers.ChoiceField(choices=TutorAvailabilitySlot.Subject.choices)
    level = serializers.CharField(max_length=80, trim_whitespace=True, min_length=2)
    starts_at = serializers.DateTimeField()
    duration_hours = serializers.IntegerField(min_value=1, max_value=LIVE_CLASS_MAX_HOURS)
    zoom_join_url = serializers.URLField(max_length=200)
    is_active = serializers.BooleanField(default=True)

    def validate_starts_at(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError("Choose a future start time.")
        return value


class TutorSlotResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    programme = serializers.CharField()
    subject = serializers.CharField()
    level = serializers.CharField()
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    duration_hours = serializers.IntegerField()
    zoom_join_url = serializers.URLField()
    is_active = serializers.BooleanField()
    price = serializers.CharField()
    reserved = serializers.BooleanField()
    editable = serializers.BooleanField()


class TutorBookingResponseSerializer(serializers.Serializer):
    reference = serializers.CharField()
    status = serializers.CharField()
    topic = serializers.CharField()
    programme = serializers.CharField()
    subject = serializers.CharField()
    level = serializers.CharField()
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    duration_hours = serializers.IntegerField()
    amount = serializers.CharField()
    student_name = serializers.CharField(allow_blank=True)
    student_email = serializers.EmailField(allow_blank=True)
    zoom_join_url = serializers.URLField(allow_blank=True)


class TutorIdentitySerializer(serializers.Serializer):
    name = serializers.CharField()
    email = serializers.EmailField()


class TutorSummarySerializer(serializers.Serializer):
    upcoming_slots = serializers.IntegerField()
    confirmed_classes = serializers.IntegerField()


class TutorDashboardResponseSerializer(serializers.Serializer):
    tutor = TutorIdentitySerializer()
    rate_per_hour = serializers.CharField()
    max_hours = serializers.IntegerField()
    slots = TutorSlotResponseSerializer(many=True)
    bookings = TutorBookingResponseSerializer(many=True)
    summary = TutorSummarySerializer()


class TutorEarningsCategorySerializer(serializers.Serializer):
    count = serializers.IntegerField()
    students = serializers.IntegerField()
    gross = serializers.DecimalField(max_digits=12, decimal_places=2)
    earned = serializers.DecimalField(max_digits=12, decimal_places=2)


class TutorEarningsResponseSerializer(serializers.Serializer):
    currency = serializers.CharField()
    categories = serializers.DictField(child=TutorEarningsCategorySerializer())
    unique_students = serializers.IntegerField()
    total = serializers.DecimalField(max_digits=12, decimal_places=2)
    paid_out = serializers.DecimalField(max_digits=12, decimal_places=2)
    outstanding = serializers.DecimalField(max_digits=12, decimal_places=2)
    classes_attended = serializers.IntegerField()
    bank_account_mask = serializers.CharField()
    recipient_verified = serializers.BooleanField()


class TutorEarningsView(TutorOnlyAPIView):
    """Amounts and aggregate paid-student counts, never student identities or bank numbers."""

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        response["Vary"] = "Authorization"
        return response

    @extend_schema(responses={200: TutorEarningsResponseSerializer})
    def get(self, request):
        from content.services.tutor_finance import tutor_dashboard_stats
        from content.tutor_finance_models import TutorPaymentProfile

        stats = tutor_dashboard_stats(request.user)
        profile = TutorPaymentProfile.objects.filter(tutor=request.user).first()
        return Response(
            {
                "currency": "ZAR",
                "categories": stats["categories"],
                "unique_students": stats["unique_students"],
                "total": stats["total"],
                "paid_out": stats["paid_out"],
                "outstanding": stats["outstanding"],
                "classes_attended": stats["classes_attended"],
                "bank_account_mask": (
                    ("****" + profile.account_last_four) if profile and profile.account_last_four else ""
                ),
                "recipient_verified": bool(profile and profile.is_active and profile.recipient_verified_at),
            }
        )


def _slot_data(slot, *, reserved=None):
    if reserved is None:
        reserved = slot.bookings.filter(status__in=RESERVED_STATUSES).exists()
    return {
        "id": slot.pk,
        "programme": slot.programme,
        "subject": slot.subject,
        "level": slot.level,
        "starts_at": slot.starts_at,
        "ends_at": slot.ends_at,
        "duration_hours": slot.duration_hours,
        "zoom_join_url": slot.zoom_join_url,
        "is_active": slot.is_active,
        "price": f"{price_for_live_class_slot(slot):.2f}",
        "reserved": reserved,
        "editable": slot.starts_at > timezone.now() and not reserved,
    }


def _save_tutor_slot(tutor, attrs, *, slot=None):
    """Serialize edits by tutor; model overlap checks remain authoritative."""
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=tutor.pk)
        if slot is None:
            slot = TutorAvailabilitySlot(tutor=tutor)
        else:
            slot = TutorAvailabilitySlot.objects.select_for_update().get(pk=slot.pk, tutor_id=tutor.pk)
            if slot.bookings.filter(status__in=RESERVED_STATUSES).exists():
                raise serializers.ValidationError(
                    {"detail": "A reserved or paid session cannot be changed. Contact the academy."}
                )
            if slot.starts_at <= timezone.now():
                raise serializers.ValidationError({"detail": "Past sessions cannot be edited."})

        for key in (
            "programme",
            "subject",
            "level",
            "starts_at",
            "zoom_join_url",
            "is_active",
        ):
            if key in attrs:
                setattr(slot, key, attrs[key])

        hours = attrs.get("duration_hours", slot.duration_hours if slot.pk else None)
        if hours is None or not 1 <= hours <= LIVE_CLASS_MAX_HOURS:
            raise serializers.ValidationError({"duration_hours": "Choose a valid number of hours."})
        slot.ends_at = slot.starts_at + timedelta(hours=hours)

        try:
            slot.full_clean()
            slot.save()
        except (DjangoValidationError, IntegrityError) as exc:
            if isinstance(exc, DjangoValidationError):
                raise serializers.ValidationError({"detail": "; ".join(exc.messages)}) from exc
            raise serializers.ValidationError({"detail": "This tutor time is no longer available."}) from exc
        return slot


class TutorDashboardView(TutorOnlyAPIView):
    @extend_schema(responses={200: TutorDashboardResponseSerializer})
    def get(self, request):
        now = timezone.now()
        slots = (
            TutorAvailabilitySlot.objects.filter(tutor=request.user)
            .annotate(
                has_reservation=Exists(
                    LiveClassBooking.objects.filter(slot_id=OuterRef("pk"), status__in=RESERVED_STATUSES)
                )
            )
            .order_by("-starts_at")[:120]
        )
        bookings = (
            LiveClassBooking.objects.filter(slot__tutor=request.user)
            .select_related("slot", "student")
            .order_by("-slot__starts_at")[:120]
        )
        items = []
        for booking in bookings:
            # Unverified payments never disclose student contact details or Zoom links.
            paid = booking.status in (
                LiveClassBooking.Status.CONFIRMED,
                LiveClassBooking.Status.COMPLETED,
            )
            items.append(
                {
                    "reference": booking.reference,
                    "status": booking.status,
                    "topic": booking.topic,
                    "programme": booking.programme,
                    "subject": booking.subject,
                    "level": booking.level,
                    "starts_at": booking.slot.starts_at,
                    "ends_at": booking.slot.ends_at,
                    "duration_hours": booking.slot.duration_hours,
                    "amount": f"{booking.amount:.2f}",
                    "student_name": (
                        f"{booking.student.first_name} {booking.student.last_name}".strip() if paid else ""
                    ),
                    "student_email": booking.student.email if paid else "",
                    "zoom_join_url": booking.slot.zoom_join_url if paid else "",
                }
            )
        return Response(
            {
                "tutor": {
                    "name": request.user.get_full_name().strip() or request.user.username,
                    "email": request.user.email,
                },
                "rate_per_hour": f"{LIVE_CLASS_PRICE:.2f}",
                "max_hours": LIVE_CLASS_MAX_HOURS,
                "slots": [_slot_data(s, reserved=s.has_reservation) for s in slots],
                "bookings": items,
                "summary": {
                    "upcoming_slots": TutorAvailabilitySlot.objects.filter(
                        tutor=request.user, starts_at__gt=now, is_active=True
                    ).count(),
                    "confirmed_classes": LiveClassBooking.objects.filter(
                        slot__tutor=request.user,
                        status=LiveClassBooking.Status.CONFIRMED,
                    ).count(),
                },
            }
        )


class TutorSlotCreateView(TutorOnlyAPIView):
    @extend_schema(request=TutorSlotWriteSerializer, responses={201: TutorSlotResponseSerializer})
    def post(self, request):
        serializer = TutorSlotWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        slot = _save_tutor_slot(request.user, serializer.validated_data)
        return Response(_slot_data(slot), status=status.HTTP_201_CREATED)


class TutorSlotUpdateView(TutorOnlyAPIView):
    @extend_schema(request=TutorSlotWriteSerializer, responses={200: TutorSlotResponseSerializer})
    def patch(self, request, slot_id: int):
        with transaction.atomic():
            try:
                owned_slot = TutorAvailabilitySlot.objects.get(pk=slot_id, tutor=request.user)
            except TutorAvailabilitySlot.DoesNotExist:
                return Response(
                    {"detail": "Tutor session not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            data = {
                "programme": owned_slot.programme,
                "subject": owned_slot.subject,
                "level": owned_slot.level,
                "starts_at": owned_slot.starts_at,
                "duration_hours": owned_slot.duration_hours,
                "zoom_join_url": owned_slot.zoom_join_url,
                "is_active": owned_slot.is_active,
            }
            data.update(request.data)
            serializer = TutorSlotWriteSerializer(data=data)
            serializer.is_valid(raise_exception=True)
            slot = _save_tutor_slot(request.user, serializer.validated_data, slot=owned_slot)
        return Response(_slot_data(slot))
