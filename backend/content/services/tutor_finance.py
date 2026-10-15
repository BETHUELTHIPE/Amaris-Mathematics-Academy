"""Server-owned tutor earnings: verified income, immutable contract snapshots, no student PII on tutor views."""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Sum, Q
from django.utils import timezone

from content.models import LiveClassBooking, Payment
from content.tutor_finance_models import (
    TutorContract, TutorCourseAssignment, TutorEarning, TutorPaymentProfile,
    TutorPayout, TutorVideoRequest,
)

CENT = Decimal("0.01")
SETTLEMENT_HOLD_DAYS = 7


class TutorRevenueError(ValueError):
    pass


def _contract_for(tutor_id, service, when):
    matching = list(
        TutorContract.objects.filter(
            tutor_id=tutor_id, service=service, is_active=True, effective_from__lte=when,
        ).filter(
            Q(effective_until__isnull=True)
            | __import__("django").db.models.Q(effective_until__gt=when)
        ).order_by("-effective_from")[:2]
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
    if (payment.status != Payment.Status.PAID or not payment.gateway_verified_at
            or payment.currency != "ZAR"):
        raise TutorRevenueError("Only verified, paid ZAR course sales qualify.")
    tutor_ids = list(
        TutorCourseAssignment.objects.filter(course=payment.course, is_active=True)
        .values_list("tutor_id", flat=True)[:2]
    )
    if len(tutor_ids) != 1:
        return None  # A service sale must have one unambiguous responsible tutor.
    return _record(
        tutor_ids[0], TutorContract.Service.COURSE, payment.reference,
        payment.course.title, payment.amount, payment.gateway_verified_at,
        delivered_at=payment.paid_at,
    )


def record_live_class_sale(booking: LiveClassBooking):
    if (booking.status != LiveClassBooking.Status.CONFIRMED or not booking.gateway_verified_at
            or not booking.paid_at or booking.currency != "ZAR"):
        raise TutorRevenueError("Only verified paid live classes qualify.")
    return _record(
        booking.slot.tutor_id, TutorContract.Service.LIVE_CLASS, booking.reference,
        f"Online class · {booking.topic}", booking.amount, booking.gateway_verified_at,
    )


def record_topical_video_sale(order: TutorVideoRequest):
    if (order.status != TutorVideoRequest.Status.PAID or not order.gateway_verified_at
            or not order.paid_at or order.currency != "ZAR"):
        raise TutorRevenueError("Only verified paid topical videos qualify.")
    return _record(
        order.tutor_id, TutorContract.Service.VIDEO, order.reference,
        f"Topical video · {order.topic}", order.price, order.gateway_verified_at,
    )


@transaction.atomic
def record_video_delivery(order: TutorVideoRequest):
    locked = TutorVideoRequest.objects.select_for_update().get(pk=order.pk)
    if locked.status not in (TutorVideoRequest.Status.PAID, TutorVideoRequest.Status.DELIVERED):
        raise TutorRevenueError("Payment must be verified before delivery.")
    if not locked.gateway_verified_at:
        raise TutorRevenueError("A payment verification timestamp is required.")
    if not locked.delivered_at:
        locked.delivered_at = timezone.now()
        locked.status = TutorVideoRequest.Status.DELIVERED
        locked.save(update_fields=["delivered_at", "status", "updated_at"])
    TutorEarning.objects.filter(
        service=TutorContract.Service.VIDEO, source_reference=locked.reference, service_delivered_at__isnull=True
    ).update(service_delivered_at=locked.delivered_at)
    return locked


@transaction.atomic
def refresh_eligible_earnings():
    """Enforce verified pay-in, delivery and a conservative refund/settlement hold."""
    cutoff = timezone.now() - timedelta(days=SETTLEMENT_HOLD_DAYS)
    ready = 0
    for earning in TutorEarning.objects.select_for_update().filter(
        state=TutorEarning.State.HELD, payment_verified_at__lte=cutoff
    ).iterator():
        if earning.service == TutorContract.Service.COURSE:
            source = Payment.objects.filter(
                reference=earning.source_reference, status=Payment.Status.PAID,
                gateway_verified_at__isnull=False
            ).first()
            delivered = bool(source and source.enrollment_id)
        elif earning.service == TutorContract.Service.LIVE_CLASS:
            source = LiveClassBooking.objects.filter(
                reference=earning.source_reference,
                status=LiveClassBooking.Status.COMPLETED,
                gateway_verified_at__isnull=False
            ).first()
            delivered = bool(source)
            if delivered and not earning.service_delivered_at:
                earning.service_delivered_at = source.slot.ends_at
        else:
            source = TutorVideoRequest.objects.filter(
                reference=earning.source_reference, status=TutorVideoRequest.Status.DELIVERED,
                gateway_verified_at__isnull=False, delivered_at__isnull=False
            ).first()
            delivered = bool(source)
            if delivered and not earning.service_delivered_at:
                earning.service_delivered_at = source.delivered_at
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
        gross=Sum("gross"), amount=Sum("tutor_amount"),
    ):
        categories[row["service"]] = {
            "count": row["paid_students"],
            "gross": row["gross"] or Decimal("0"),
            "earned": row["amount"] or Decimal("0"),
        }
    total = sum((row["earned"] for row in categories.values()), Decimal("0"))
    sent = earnings.filter(state=TutorEarning.State.PAID).aggregate(value=Sum("tutor_amount"))["value"] or Decimal("0")
    awaiting = earnings.exclude(state=TutorEarning.State.PAID).aggregate(value=Sum("tutor_amount"))["value"] or Decimal("0")
    attended = LiveClassBooking.objects.filter(
        slot__tutor=tutor, status=LiveClassBooking.Status.COMPLETED,
        gateway_verified_at__isnull=False
    ).count()
    return {
        "categories": categories, "total": total, "paid_out": sent,
        "outstanding": awaiting, "classes_attended": attended,
        "recent": earnings.order_by("-payment_verified_at").values(
            "service", "service_label", "gross", "tutor_amount", "state", "payment_verified_at"
        )[:15],
    }
