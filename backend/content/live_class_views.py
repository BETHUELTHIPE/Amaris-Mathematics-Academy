from __future__ import annotations

from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import SupabaseStudentAuthentication
from .models import LiveClassBooking, TutorAvailabilitySlot
from .services.live_classes import create_live_class_checkout
from .services.payments import PaymentSecurityError


class LiveClassSlotFilterSerializer(serializers.Serializer):
    programme = serializers.ChoiceField(
        choices=TutorAvailabilitySlot.Programme.choices,
        required=False,
    )
    subject = serializers.ChoiceField(
        choices=TutorAvailabilitySlot.Subject.choices,
        required=False,
    )
    level = serializers.CharField(max_length=80, required=False, trim_whitespace=True)


class LiveClassSlotResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    programme = serializers.CharField()
    programme_label = serializers.CharField()
    subject = serializers.CharField()
    subject_label = serializers.CharField()
    level = serializers.CharField()
    tutor = serializers.CharField()
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    duration_minutes = serializers.IntegerField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField()


class LiveClassSlotView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(
        parameters=[LiveClassSlotFilterSerializer],
        responses={200: LiveClassSlotResponseSerializer(many=True)},
    )
    def get(self, request):
        filters = LiveClassSlotFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        values = filters.validated_data
        now = timezone.now()

        LiveClassBooking.objects.filter(
            status=LiveClassBooking.Status.PENDING_PAYMENT,
            hold_expires_at__lte=now,
        ).update(status=LiveClassBooking.Status.EXPIRED)

        queryset = (
            TutorAvailabilitySlot.objects.filter(
                is_active=True,
                starts_at__gt=now,
            )
            .select_related("tutor")
            .exclude(
                Q(bookings__status=LiveClassBooking.Status.CONFIRMED)
                | Q(
                    bookings__status=LiveClassBooking.Status.PENDING_PAYMENT,
                    bookings__hold_expires_at__gt=now,
                )
            )
            .distinct()
        )
        if values.get("programme"):
            queryset = queryset.filter(programme=values["programme"])
        if values.get("subject"):
            queryset = queryset.filter(subject=values["subject"])
        if values.get("level"):
            queryset = queryset.filter(level__iexact=values["level"])
        queryset = queryset.order_by("starts_at")[:100]

        payload = [
            {
                "id": str(slot.pk),
                "programme": slot.programme,
                "programme_label": slot.get_programme_display(),
                "subject": slot.subject,
                "subject_label": slot.get_subject_display(),
                "level": slot.level,
                "tutor": slot.tutor_display_name,
                "starts_at": slot.starts_at,
                "ends_at": slot.ends_at,
                "duration_minutes": max(
                    0,
                    int((slot.ends_at - slot.starts_at).total_seconds() // 60),
                ),
                "price": "250.00",
                "currency": "ZAR",
            }
            for slot in queryset
        ]
        return Response(payload)


class LiveClassCheckoutRequestSerializer(serializers.Serializer):
    slot_id = serializers.UUIDField()
    topic = serializers.CharField(min_length=2, max_length=180, trim_whitespace=True)
    idempotency_key = serializers.RegexField(r"^[A-Za-z0-9_-]{8,64}$")


class LiveClassCheckoutResponseSerializer(serializers.Serializer):
    booking_reference = serializers.CharField()
    status = serializers.CharField()
    gateway_url = serializers.URLField()
    fields = serializers.DictField(child=serializers.CharField())
    booking = serializers.DictField()


class LiveClassBookingStatusSerializer(serializers.Serializer):
    booking_reference = serializers.CharField()
    status = serializers.CharField()
    programme = serializers.CharField()
    subject = serializers.CharField()
    level = serializers.CharField()
    topic = serializers.CharField()
    tutor = serializers.CharField()
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField()
    invoice_number = serializers.CharField(allow_blank=True, allow_null=True)
    zoom_join_url = serializers.URLField(allow_blank=True)


class LiveClassStudentAPIView(APIView):
    authentication_classes = (SupabaseStudentAuthentication,)
    permission_classes = (IsAuthenticated,)

    @property
    def student(self):
        return self.request.user.student


class LiveClassCheckoutView(LiveClassStudentAPIView):
    @extend_schema(
        request=LiveClassCheckoutRequestSerializer,
        responses={201: LiveClassCheckoutResponseSerializer},
    )
    def post(self, request):
        serializer = LiveClassCheckoutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        try:
            slot = TutorAvailabilitySlot.objects.select_related("tutor").get(
                pk=values["slot_id"],
                is_active=True,
            )
        except TutorAvailabilitySlot.DoesNotExist:
            return Response(
                {"detail": "This tutor slot is not available."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            checkout = create_live_class_checkout(
                student=request.user.student,
                slot=slot,
                topic=values["topic"],
                idempotency_key=values["idempotency_key"],
            )
        except PaymentSecurityError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc

        booking = LiveClassBooking.objects.select_related("slot", "slot__tutor").get(
            reference=checkout.booking_reference
        )
        return Response(
            {
                "booking_reference": booking.reference,
                "status": booking.status,
                "gateway_url": checkout.gateway_url,
                "fields": checkout.fields,
                "booking": {
                    "programme": booking.get_programme_display(),
                    "subject": booking.get_subject_display(),
                    "level": booking.level,
                    "topic": booking.topic,
                    "tutor": booking.slot.tutor_display_name,
                    "starts_at": booking.slot.starts_at,
                    "ends_at": booking.slot.ends_at,
                    "amount": f"{booking.amount:.2f}",
                    "currency": booking.currency,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class LiveClassBookingStatusView(LiveClassStudentAPIView):
    @extend_schema(responses={200: LiveClassBookingStatusSerializer})
    def get(self, request, reference: str):
        try:
            booking = LiveClassBooking.objects.select_related(
                "slot",
                "slot__tutor",
            ).get(
                reference=reference,
                student=request.user.student,
            )
        except LiveClassBooking.DoesNotExist:
            return Response(
                {"detail": "Live-class booking not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "booking_reference": booking.reference,
                "status": booking.status,
                "programme": booking.get_programme_display(),
                "subject": booking.get_subject_display(),
                "level": booking.level,
                "topic": booking.topic,
                "tutor": booking.slot.tutor_display_name,
                "starts_at": booking.slot.starts_at,
                "ends_at": booking.slot.ends_at,
                "amount": booking.amount,
                "currency": booking.currency,
                "invoice_number": booking.invoice_number,
                "zoom_join_url": (
                    booking.slot.zoom_join_url if booking.status == LiveClassBooking.Status.CONFIRMED else ""
                ),
            }
        )
