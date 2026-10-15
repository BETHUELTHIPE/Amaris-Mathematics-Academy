"""Scheduled reconciliation: no bank transfer without a verified provider integration."""

from celery import shared_task
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from content.models import LiveClassBooking, Payment
from content.tutor_finance_models import TutorEarning, TutorPayout, TutorVideoRequest
from content.services.tutor_finance import (
    record_course_sale,
    record_live_class_sale,
    record_topical_video_sale,
    refresh_eligible_earnings,
)


@shared_task(ignore_result=True)
def reconcile_tutor_earnings():
    """Repair missing ledger rows and apply delivery/settlement safeguards."""
    # Bounded batches; idempotent unique source keys protect against callback replay.
    for payment in (
        Payment.objects.filter(status=Payment.Status.PAID, gateway_verified_at__isnull=False)
        .select_related("student", "course")
        .order_by("-paid_at")[:200]
    ):
        if not TutorEarning.objects.filter(service="course", source_reference=payment.reference).exists():
            record_course_sale(payment)
    for booking in (
        LiveClassBooking.objects.filter(
            status__in=[LiveClassBooking.Status.CONFIRMED, LiveClassBooking.Status.COMPLETED],
            gateway_verified_at__isnull=False,
        )
        .select_related("student", "slot")
        .order_by("-paid_at")[:200]
    ):
        if not TutorEarning.objects.filter(service="live_class", source_reference=booking.reference).exists():
            # The original record function only processes confirmed bookings; completed ones are handled via a copy-free status check.
            if booking.status == LiveClassBooking.Status.CONFIRMED:
                record_live_class_sale(booking)
    for order in TutorVideoRequest.objects.filter(
        status=TutorVideoRequest.Status.PAID, gateway_verified_at__isnull=False
    ).order_by("-paid_at")[:200]:
        if not TutorEarning.objects.filter(service="video", source_reference=order.reference).exists():
            record_topical_video_sale(order)

    # Refund and cancellation corrections MUST NOT silently claw back a bank transfer.
    for earning in TutorEarning.objects.filter(state__in=[TutorEarning.State.HELD, TutorEarning.State.READY]):
        reversed_source = (
            (
                earning.service == "course"
                and Payment.objects.filter(reference=earning.source_reference, status=Payment.Status.REFUNDED).exists()
            )
            or (
                earning.service == "video"
                and TutorVideoRequest.objects.filter(
                    reference=earning.source_reference, status=TutorVideoRequest.Status.REFUNDED
                ).exists()
            )
            or (
                earning.service == "live_class"
                and LiveClassBooking.objects.filter(
                    reference=earning.source_reference, status=LiveClassBooking.Status.CANCELLED
                ).exists()
            )
        )
        if reversed_source:
            earning.state = TutorEarning.State.REVERSED
            earning.save(update_fields=["state", "updated_at"])
    return refresh_eligible_earnings()


@shared_task(
    bind=True, ignore_result=True, autoretry_for=(OSError,), retry_backoff=True, retry_kwargs={"max_retries": 5}
)
def email_tutor_payout_receipt(_self):
    """Email POP only after trusted provider settlement has been recorded.

    This worker cannot initiate or declare transfers. A separately verified payout
    adapter must write state=paid, confirmed_at and provider_reference atomically.
    """
    with transaction.atomic():
        payout = (
            TutorPayout.objects.select_for_update(skip_locked=True)
            .select_related("earning", "earning__tutor")
            .filter(state=TutorPayout.State.PAID, confirmed_at__isnull=False, receipt_emailed_at__isnull=True)
            .exclude(provider_reference="")
            .order_by("confirmed_at")
            .first()
        )
        if payout is None:
            return 0
        tutor = payout.earning.tutor
        if not tutor.email:
            return 0
        sent = send_mail(
            subject="Amaris tutor payment confirmation",
            message=(
                f"Dear {tutor.get_full_name().strip() or tutor.get_username()},\n\n"
                "Your tutor payout has been confirmed by the payment provider.\n"
                f"Service: {payout.earning.get_service_display()}\n"
                f"Service reference: {payout.earning.source_reference}\n"
                f"Amount paid: R {payout.earning.tutor_amount:.2f}\n"
                f"Provider: {payout.provider_name}\n"
                f"Transfer reference: {payout.provider_reference}\n"
                f"Payment date: {timezone.localtime(payout.confirmed_at):%d %B %Y}\n"
                f"Destination account: ****{payout.bank_last_four}\n\n"
                "This confirmation is issued only after provider verification.\n"
                "Amaris Mathematics Academy"
            ),
            from_email=None,
            recipient_list=[tutor.email],
            fail_silently=False,
        )
        if sent != 1:
            raise OSError("The mail provider did not accept the payment notification.")
        payout.receipt_emailed_at = timezone.now()
        payout.save(update_fields=["receipt_emailed_at", "updated_at"])
    return 1
