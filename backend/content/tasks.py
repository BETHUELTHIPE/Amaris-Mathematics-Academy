from datetime import timedelta
from html import escape

from celery import shared_task
from django.apps import apps
from django.core.mail import EmailMultiAlternatives, send_mail
from django.db import transaction
from django.db.utils import InterfaceError, OperationalError
from django.utils import timezone

from content.models import LiveClassBooking, SiteSettings
from content.payment_models import NotificationOutbox
from content.services.reconciliation import reconcile_verified_payments


@shared_task(
    bind=True,
    ignore_result=True,
    autoretry_for=(OperationalError, InterfaceError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    retry_kwargs={"max_retries": 6},
)
def publish_scheduled_content(_self) -> dict[str, int]:
    now = timezone.now()
    published: dict[str, int] = {}
    for model_name in (
        "Page",
        "PageSection",
        "PricingPlan",
        "Testimonial",
        "FAQ",
        "Announcement",
        "VideoAsset",
        "Lesson",
        "ResourceAsset",
    ):
        model = apps.get_model("content", model_name)
        count = model.objects.filter(is_published=False, publish_at__isnull=False, publish_at__lte=now).update(
            is_published=True
        )
        published[model_name] = count

    course_model = apps.get_model("content", "Course")
    course_count = course_model.objects.filter(
        status=course_model.Status.REVIEW,
        publish_at__isnull=False,
        publish_at__lte=now,
    ).update(status=course_model.Status.PUBLISHED, is_published=True)
    published["Course"] = course_count
    return published


@shared_task(
    bind=True,
    ignore_result=True,
    autoretry_for=(OperationalError, InterfaceError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    retry_kwargs={"max_retries": 6},
)
def reconcile_payments(_self) -> None:
    reconcile_verified_payments()


@shared_task(
    bind=True,
    ignore_result=True,
    autoretry_for=(OSError,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    retry_kwargs={"max_retries": 6},
)
def deliver_transactional_email(_self) -> int:
    """Deliver one queued payment email.

    The row remains queued if SMTP raises so Celery retry is safe. The
    transaction lock prevents multiple notification workers from sending the
    same outbox record concurrently.
    """

    with transaction.atomic():
        outbox = (
            NotificationOutbox.objects.select_for_update(skip_locked=True)
            .select_related("payment", "payment__course")
            .filter(status=NotificationOutbox.Status.QUEUED)
            .order_by("created_at")
            .first()
        )
        if outbox is None:
            return 0

        payload = outbox.payload or {}
        course = str(payload.get("course") or outbox.payment.course.title)
        invoice_number = str(payload.get("invoice_number") or "")
        ticket_number = str(payload.get("ticket_number") or "")
        subject = f"Amaris payment confirmed — {course}"
        message = (
            "Your PayFast payment has been verified and your course access is active.\n\n"
            f"Course: {course}\n"
            f"Payment reference: {outbox.payment.reference}\n"
            f"Invoice: {invoice_number}\n"
            f"Ticket: {ticket_number}\n\n"
            "Log in to your Amaris student dashboard to continue learning."
        )
        sent = send_mail(
            subject=subject,
            message=message,
            from_email=None,
            recipient_list=[outbox.destination],
            fail_silently=False,
        )
        if sent != 1:
            raise OSError("Transactional email backend did not accept the message.")

        outbox.status = NotificationOutbox.Status.SENT
        outbox.save(update_fields=["status", "updated_at"])
        return 1



def _live_class_brand() -> tuple[str, str, str]:
    site = SiteSettings.objects.first()
    name = site.site_name if site else "Amaris Mathematics Academy"
    email = site.email if site else "bethuelmoukangwe8@gmail.com"
    phone = site.phone if site else "071 415 6665"
    return name, email, phone


def _booking_when(booking: LiveClassBooking) -> str:
    starts_at = timezone.localtime(booking.slot.starts_at)
    return starts_at.strftime("%A, %d %B %Y at %H:%M")


def _send_live_class_message(
    booking: LiveClassBooking,
    *,
    subject: str,
    heading: str,
    body_lines: list[str],
    attach_invoice: bool = False,
) -> None:
    name, email, phone = _live_class_brand()
    text = "\n".join(
        [
            name,
            f"{email} | {phone}",
            "",
            heading,
            "",
            *body_lines,
        ]
    )
    html_lines = "".join(f"<p>{escape(line)}</p>" for line in body_lines)
    html = (
        '<div style="font-family:Arial,sans-serif;max-width:680px;margin:auto;'
        'border:1px solid #dce4ef;border-radius:18px;overflow:hidden">'
        '<div style="background:#07152d;color:#fff;padding:24px">'
        f'<div style="font-size:22px;font-weight:700">{escape(name)}</div>'
        f'<div style="margin-top:6px;color:#dce4ef">{escape(email)} · {escape(phone)}</div>'
        "</div>"
        '<div style="padding:28px;color:#1d2d44">'
        f'<h1 style="font-size:24px;margin-top:0">{escape(heading)}</h1>'
        f"{html_lines}"
        "</div></div>"
    )
    message = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=None,
        to=[booking.student.email],
    )
    message.attach_alternative(html, "text/html")
    if attach_invoice and booking.invoice_number:
        invoice_text = "\n".join(
            [
                name,
                "LIVE CLASS INVOICE",
                f"Invoice: {booking.invoice_number}",
                f"Booking: {booking.reference}",
                f"Student: {booking.student.first_name} {booking.student.last_name}",
                f"Programme: {booking.get_programme_display()}",
                f"Subject: {booking.get_subject_display()}",
                f"Level: {booking.level}",
                f"Topic: {booking.topic}",
                f"Tutor: {booking.slot.tutor_display_name}",
                f"Class: {_booking_when(booking)}",
                f"Amount: R{booking.amount:.2f}",
                f"Currency: {booking.currency}",
                "Payment status: Paid and verified by PayFast",
            ]
        )
        message.attach(
            f"{booking.invoice_number}.txt",
            invoice_text,
            "text/plain",
        )
    sent = message.send(fail_silently=False)
    if sent != 1:
        raise OSError("Transactional email backend did not accept the live-class message.")


@shared_task(
    bind=True,
    ignore_result=True,
    autoretry_for=(OSError, OperationalError, InterfaceError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    retry_kwargs={"max_retries": 6},
)
def deliver_live_class_confirmation(_self) -> int:
    with transaction.atomic():
        booking = (
            LiveClassBooking.objects.select_for_update(skip_locked=True)
            .select_related("student", "slot", "slot__tutor")
            .filter(
                status=LiveClassBooking.Status.CONFIRMED,
                confirmation_sent_at__isnull=True,
            )
            .order_by("paid_at", "created_at")
            .first()
        )
        if booking is None:
            return 0

        _send_live_class_message(
            booking,
            subject=f"Amaris live class confirmed — {booking.reference}",
            heading="Your Zoom live class is confirmed",
            body_lines=[
                f"Programme: {booking.get_programme_display()}",
                f"Subject: {booking.get_subject_display()}",
                f"Level: {booking.level}",
                f"Topic: {booking.topic}",
                f"Tutor: {booking.slot.tutor_display_name}",
                f"Date and time: {_booking_when(booking)}",
                f"Zoom link: {booking.slot.zoom_join_url}",
                f"Invoice: {booking.invoice_number}",
                f"Amount paid: R{booking.amount:.2f}",
            ],
            attach_invoice=True,
        )
        booking.confirmation_sent_at = timezone.now()
        booking.save(update_fields=("confirmation_sent_at", "updated_at"))
        return 1


@shared_task(
    bind=True,
    ignore_result=True,
    autoretry_for=(OSError, OperationalError, InterfaceError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    retry_kwargs={"max_retries": 6},
)
def deliver_live_class_reminder(_self) -> int:
    now = timezone.now()
    with transaction.atomic():
        booking = (
            LiveClassBooking.objects.select_for_update(skip_locked=True)
            .select_related("student", "slot", "slot__tutor")
            .filter(
                status=LiveClassBooking.Status.CONFIRMED,
                confirmation_sent_at__isnull=False,
                reminder_sent_at__isnull=True,
                slot__starts_at__gt=now,
                slot__starts_at__lte=now + timedelta(minutes=30),
            )
            .order_by("slot__starts_at")
            .first()
        )
        if booking is None:
            return 0

        _send_live_class_message(
            booking,
            subject=f"Reminder: your Amaris Zoom class starts in 30 minutes",
            heading="Your live class starts soon",
            body_lines=[
                f"Topic: {booking.topic}",
                f"Tutor: {booking.slot.tutor_display_name}",
                f"Start time: {_booking_when(booking)}",
                f"Zoom link: {booking.slot.zoom_join_url}",
                f"Booking reference: {booking.reference}",
            ],
        )
        booking.reminder_sent_at = timezone.now()
        booking.save(update_fields=("reminder_sent_at", "updated_at"))
        return 1


@shared_task(
    bind=True,
    ignore_result=True,
    autoretry_for=(OperationalError, InterfaceError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    retry_kwargs={"max_retries": 6},
)
def expire_live_class_holds(_self) -> int:
    return LiveClassBooking.objects.filter(
        status=LiveClassBooking.Status.PENDING_PAYMENT,
        hold_expires_at__lte=timezone.now(),
    ).update(status=LiveClassBooking.Status.EXPIRED)
