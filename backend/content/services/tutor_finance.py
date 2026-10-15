"""Server-owned tutor earnings: verified income, immutable contract snapshots, no student PII on tutor views."""

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from content.models import LiveClassBooking, Payment, VideoRequest
from content.tutor_finance_models import (
    TutorContract,
    TutorCourseAssignment,
    TutorEarning,
    TutorPayout,
)

CENT = Decimal("0.01")
SETTLEMENT_HOLD_DAYS = 7


class TutorRevenueError(ValueError):
    pass


def _contract_for(tutor_id, service, when):
    matching = list(
        TutorContract.objects.filter(
            tutor_id=tutor_id,
            service=service,
            is_active=True,
            effective_from__lte=when,
        )
        .filter(Q(effective_until__isnull=True) | Q(effective_until__gt=when))
        .order_by("-effective_from")[:2]
    )
    if len(matching) != 1:
        return None
    return matching[0]


def _record(tutor_id, service, source_reference, label, amount, paid_at, *, delivered_at=None):
    """Called ONLY after a verified provider notification, inside the caller's transaction."""
    if paid_at is None:
        raise TutorRevenueError("Gateway payment verification is required.")
    if amount <= 0:
        raise TutorRevenueError("Negative or zero revenue is not eligible.")
    if TutorEarning.objects.filter(service=service, source_reference=source_reference).exists():
        return TutorEarning.objects.get(service=service, source_reference=source_reference)
    contract = _contract_for(tutor_id, service, paid_at)
    if not contract:
        return None  # No guessed contract; admin must resolve this sale.
    tutor_amount = (amount * contract.tutor_percent / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
    earning, _ = TutorEarning.objects.get_or_create(
        service=service,
        source_reference=source_reference,
        defaults=dict(
            tutor_id=tutor_id,
            contract=contract,
            service_label=label[:180],
            gross=amount,
            tutor_percent=contract.tutor_percent,
            tutor_amount=tutor_amount,
            academy_amount=amount - tutor_amount,
            payment_verified_at=paid_at,
            service_delivered_at=delivered_at,
            currency="ZAR",
            state=TutorEarning.State.HELD,
        ),
    )
    if earning.tutor_id != tutor_id or earning.gross != amount:
        raise TutorRevenueError("Sale source is bound to a different tutor or amount.")
    return earning


def record_course_sale(payment: Payment):
    if payment.status != Payment.Status.PAID or not payment.gateway_verified_at or payment.currency != "ZAR":
        raise TutorRevenueError("Only verified, paid ZAR course sales qualify.")
    tutor_ids = list(
        TutorCourseAssignment.objects.filter(course=payment.course, is_active=True).values_list("tutor_id", flat=True)[
            :2
        ]
    )
    if len(tutor_ids) != 1:
        return None  # A service sale must have one unambiguous responsible tutor.
    return _record(
        tutor_ids[0],
        TutorContract.Service.COURSE,
        payment.reference,
        payment.course.title,
        payment.amount,
        payment.gateway_verified_at,
        delivered_at=payment.paid_at,
    )


def record_live_class_sale(booking: LiveClassBooking):
    if (
        booking.status != LiveClassBooking.Status.CONFIRMED
        or not booking.gateway_verified_at
        or not booking.paid_at
        or booking.currency != "ZAR"
    ):
        raise TutorRevenueError("Only verified paid live classes qualify.")
    return _record(
        booking.slot.tutor_id,
        TutorContract.Service.LIVE_CLASS,
        booking.reference,
        f"Online class · {booking.topic}",
        booking.amount,
        booking.gateway_verified_at,
    )


def record_existing_video_sale(order: VideoRequest):
    """Use the existing production video-request checkout, never create a second charge."""
    eligible_statuses = (
        VideoRequest.Status.QUEUED,
        VideoRequest.Status.TUTOR_ASSIGNED,
        VideoRequest.Status.RECORDING,
        VideoRequest.Status.PROCESSING,
        VideoRequest.Status.REVIEW,
        VideoRequest.Status.READY,
    )
    if (
        order.status not in eligible_statuses
        or not order.gateway_verified_at
        or not order.paid_at
        or order.currency != "ZAR"
        or not order.assigned_tutor_id
    ):
        return None
    return _record(
        order.assigned_tutor_id,
        TutorContract.Service.VIDEO,
        order.reference,
        f"Video request · {order.topic}",
        order.amount,
        order.gateway_verified_at,
        delivered_at=order.video_ready_at if order.status == VideoRequest.Status.READY else None,
    )


@transaction.atomic
def refresh_eligible_earnings():
    """Enforce verified pay-in, delivery and a conservative refund/settlement hold."""
    cutoff = timezone.now() - timedelta(days=SETTLEMENT_HOLD_DAYS)
    ready = 0
    for earning in (
        TutorEarning.objects.select_for_update()
        .filter(state=TutorEarning.State.HELD, payment_verified_at__lte=cutoff)
        .iterator()
    ):
        if earning.service == TutorContract.Service.COURSE:
            source = Payment.objects.filter(
                reference=earning.source_reference, status=Payment.Status.PAID, gateway_verified_at__isnull=False
            ).first()
            delivered = bool(source and source.enrollment_id)
        elif earning.service == TutorContract.Service.LIVE_CLASS:
            booking_source = LiveClassBooking.objects.filter(
                reference=earning.source_reference,
                status=LiveClassBooking.Status.COMPLETED,
                gateway_verified_at__isnull=False,
            ).first()
            delivered = bool(booking_source)
            if booking_source and not earning.service_delivered_at:
                earning.service_delivered_at = booking_source.slot.ends_at
        else:
            video_source = (
                VideoRequest.objects.filter(
                    reference=earning.source_reference,
                    status=VideoRequest.Status.READY,
                    gateway_verified_at__isnull=False,
                    video_ready_at__isnull=False,
                )
                .exclude(video_external_id="")
                .first()
            )
            delivered = bool(video_source)
            if video_source and not earning.service_delivered_at:
                earning.service_delivered_at = video_source.video_ready_at
        if not delivered:
            continue
        earning.state = TutorEarning.State.READY
        earning.eligible_at = timezone.now()
        earning.save(update_fields=["state", "eligible_at", "service_delivered_at", "updated_at"])
        TutorPayout.objects.get_or_create(earning=earning)
        ready += 1
    return ready


def tutor_dashboard_stats(tutor):
    """Only aggregate service/category totals and this tutor's own payout ledger."""
    earnings = TutorEarning.objects.filter(tutor=tutor).exclude(state=TutorEarning.State.REVERSED)
    categories = {
        service: {"count": 0, "gross": Decimal("0"), "earned": Decimal("0")}
        for service, _ in TutorContract.Service.choices
    }
    for row in earnings.values("service").annotate(
        paid_students=Count("source_reference", distinct=True),
        gross=Sum("gross"),
        amount=Sum("tutor_amount"),
    ):
        categories[row["service"]] = {
            "count": row["paid_students"],
            "gross": row["gross"] or Decimal("0"),
            "earned": row["amount"] or Decimal("0"),
        }
    # Distinct paying-student counts (aggregates only; never serialize identity).
    course_sources = earnings.filter(service="course").values_list("source_reference", flat=True)
    class_sources = earnings.filter(service="live_class").values_list("source_reference", flat=True)
    video_sources = earnings.filter(service="video").values_list("source_reference", flat=True)
    people = {
        "course": set(Payment.objects.filter(reference__in=course_sources).values_list("student_id", flat=True)),
        "live_class": set(
            LiveClassBooking.objects.filter(reference__in=class_sources).values_list("student_id", flat=True)
        ),
        "video": set(VideoRequest.objects.filter(reference__in=video_sources).values_list("student_id", flat=True)),
    }
    for service, student_ids in people.items():
        categories[service]["students"] = len(student_ids)
    unique_students = len(set().union(*people.values()))
    total = sum((Decimal(str(row["earned"])) for row in categories.values()), Decimal("0"))
    sent = earnings.filter(state=TutorEarning.State.PAID).aggregate(value=Sum("tutor_amount"))["value"] or Decimal("0")
    awaiting = earnings.exclude(state=TutorEarning.State.PAID).aggregate(value=Sum("tutor_amount"))["value"] or Decimal(
        "0"
    )
    attended = LiveClassBooking.objects.filter(
        slot__tutor=tutor, status=LiveClassBooking.Status.COMPLETED, gateway_verified_at__isnull=False
    ).count()
    return {
        "categories": categories,
        "unique_students": unique_students,
        "total": total,
        "paid_out": sent,
        "outstanding": awaiting,
        "classes_attended": attended,
        "recent": earnings.order_by("-payment_verified_at").values(
            "service", "service_label", "gross", "tutor_amount", "state", "payment_verified_at"
        )[:15],
    }
