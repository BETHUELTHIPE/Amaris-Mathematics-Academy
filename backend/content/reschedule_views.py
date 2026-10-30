"""Protected rescheduling endpoints for paid, future live-class bookings."""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from content.authentication import SupabaseStudentAuthentication
from content.models import LiveClassBooking, TutorAvailabilitySlot
from content.reschedule_tasks import notify_reschedule


class RescheduleSerializer(serializers.Serializer):
    slot_id = serializers.UUIDField()
    reason = serializers.CharField(max_length=500, allow_blank=True, required=False)


def move_booking(*, reference, new_slot_id, actor, actor_id, reason):
    """Keep payment and invoice; atomically replace only the booked slot."""
    with transaction.atomic():
        booking = (
            LiveClassBooking.objects.select_for_update()
            .select_related("slot", "student")
            .filter(reference=reference)
            .first()
        )
        if booking is None:
            return Response({"detail": "Booking not found."}, status=404)
        if actor == "student" and booking.student_id != actor_id:
            return Response({"detail": "Booking not found."}, status=404)
        if actor == "tutor" and booking.slot.tutor_id != actor_id:
            return Response({"detail": "Booking not found."}, status=404)
        now = timezone.now()
        if (
            booking.status != LiveClassBooking.Status.CONFIRMED
            or not booking.paid_at
            or booking.slot.starts_at <= now + timedelta(hours=24)
        ):
            return Response({"detail": "Only confirmed paid bookings at least 24 hours ahead can be rescheduled."}, status=409)
        slots = TutorAvailabilitySlot.objects.select_for_update().filter(pk=new_slot_id, is_active=True)
        new_slot = slots.first()
        if new_slot is None or new_slot.pk == booking.slot_id:
            return Response({"detail": "Select a different available time slot."}, status=409)
        if (
            new_slot.tutor_id != booking.slot.tutor_id
            or new_slot.programme != booking.programme
            or new_slot.subject != booking.subject
            or new_slot.level != booking.level
            or new_slot.starts_at <= now + timedelta(hours=24)
            or (new_slot.ends_at - new_slot.starts_at) != (booking.slot.ends_at - booking.slot.starts_at)
        ):
            return Response({"detail": "Choose a future slot with the same tutor, subject, level and duration."}, status=409)
        if TutorAvailabilitySlot.objects.filter(
            tutor_id=new_slot.tutor_id,
            starts_at__lt=new_slot.ends_at,
            ends_at__gt=new_slot.starts_at,
            bookings__status__in=[LiveClassBooking.Status.CONFIRMED, LiveClassBooking.Status.PENDING_PAYMENT],
        ).exclude(pk=booking.slot_id).exists():
            return Response({"detail": "The tutor is already booked at that time."}, status=409)
        if LiveClassBooking.objects.filter(
            slot=new_slot,
            status__in=[LiveClassBooking.Status.CONFIRMED, LiveClassBooking.Status.PENDING_PAYMENT],
        ).exclude(pk=booking.pk).exists():
            return Response({"detail": "This slot is no longer available."}, status=409)
        old_slot = booking.slot
        booking.slot = new_slot
        booking.reminder_sent_at = None
        try:
            booking.save(update_fields=["slot", "reminder_sent_at", "updated_at"])
        except IntegrityError:
            return Response({"detail": "This slot was just taken. Please select another."}, status=409)
        transaction.on_commit(
            lambda: notify_reschedule.delay(
                str(booking.pk), old_slot.starts_at.isoformat(), actor, reason
            )
        )
    return Response({
        "booking_reference": booking.reference,
        "status": "rescheduled",
        "starts_at": new_slot.starts_at,
        "ends_at": new_slot.ends_at,
        "tutor": new_slot.tutor_display_name,
    })


class StudentRescheduleView(APIView):
    authentication_classes = (SupabaseStudentAuthentication,)
    permission_classes = (IsAuthenticated,)

    def post(self, request, reference):
        serializer = RescheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return move_booking(
            reference=reference,
            new_slot_id=serializer.validated_data["slot_id"],
            reason=serializer.validated_data.get("reason", ""),
            actor="student",
            actor_id=request.user.student.pk,
        )


class TutorRescheduleView(APIView):
    """For authenticated Django tutor accounts; requires same tutor ownership."""
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsAuthenticated,)

    def post(self, request, reference):
        serializer = RescheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return move_booking(
            reference=reference,
            new_slot_id=serializer.validated_data["slot_id"],
            reason=serializer.validated_data.get("reason", ""),
            actor="tutor",
            actor_id=request.user.pk,
        )
