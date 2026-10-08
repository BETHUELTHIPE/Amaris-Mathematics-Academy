from datetime import timedelta
from html import escape

from botocore.exceptions import BotoCoreError, ClientError
from celery import shared_task
from django.apps import apps
from django.core.files.storage import storages
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.utils import InterfaceError, OperationalError
from django.utils import timezone

from content.models import LiveClassBooking, SiteSettings, VideoRequest
from content.payment_models import Invoice, NotificationOutbox
from content.services.invoices import archive_invoice_pdf, mark_invoice_archive_failure
from content.services.reconciliation import reconcile_verified_payments
from content.services.video_requests import video_request_eta, video_request_queue_position


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
        email = EmailMultiAlternatives(
            subject=subject,
            body=message,
            from_email=None,
            to=[outbox.destination],
        )
        invoice = outbox.payment.invoice
        email.attach(f"{invoice.invoice_number}.pdf", archive_invoice_pdf(invoice), "application/pdf")
        sent = email.send(fail_silently=False)
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
        message.attach(
            f"{booking.invoice_number}.pdf",
            archive_invoice_pdf(booking),
            "application/pdf",
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
    delivered = 0
    for _ in range(100):
        if not _deliver_one_live_class_confirmation():
            break
        delivered += 1
    return delivered


def _deliver_one_live_class_confirmation() -> bool:
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
            return False

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
        return True


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
    delivered = 0
    for _ in range(100):
        if not _deliver_one_live_class_reminder():
            break
        delivered += 1
    return delivered


def _deliver_one_live_class_reminder() -> bool:
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
            return False

        _send_live_class_message(
            booking,
            subject="Reminder: your Amaris Zoom class starts in 30 minutes",
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
        return True


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


def _send_video_request_message(
    request: VideoRequest,
    *,
    subject: str,
    heading: str,
    body_lines: list[str],
    attach_invoice: bool = False,
) -> None:
    name, email, phone = _live_class_brand()
    text = "\n".join([name, f"{email} | {phone}", "", heading, "", *body_lines])
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
    message = EmailMultiAlternatives(subject=subject, body=text, from_email=None, to=[request.student.email])
    message.attach_alternative(html, "text/html")
    if attach_invoice and request.invoice_number:
        message.attach(
            f"{request.invoice_number}.pdf",
            archive_invoice_pdf(request),
            "application/pdf",
        )
    sent = message.send(fail_silently=False)
    if sent != 1:
        raise OSError("Transactional email backend did not accept the video-request message.")


@shared_task(
    bind=True,
    ignore_result=True,
    autoretry_for=(OSError, OperationalError, InterfaceError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    retry_kwargs={"max_retries": 6},
)
def deliver_video_request_notifications(_self) -> int:
    delivered = 0
    for _ in range(100):
        if not _deliver_one_video_request_notification():
            break
        delivered += 1
    return delivered


def _deliver_one_video_request_notification() -> bool:
    with transaction.atomic():
        item = (
            VideoRequest.objects.select_for_update(skip_locked=True)
            .select_related("student", "assigned_tutor")
            .filter(status=VideoRequest.Status.QUEUED, confirmation_sent_at__isnull=True)
            .order_by("queue_entered_at")
            .first()
        )
        event = "confirmation"
        if item is None:
            for candidate in (
                VideoRequest.objects.select_for_update(skip_locked=True)
                .select_related("student", "assigned_tutor")
                .filter(status=VideoRequest.Status.QUEUED, position_one_sent_at__isnull=True)
                .order_by("queue_entered_at")[:25]
            ):
                if video_request_queue_position(candidate) == 1:
                    item = candidate
                    event = "position_one"
                    break
        if item is None:
            item = (
                VideoRequest.objects.select_for_update(skip_locked=True)
                .select_related("student", "assigned_tutor")
                .filter(status=VideoRequest.Status.RECORDING, recording_sent_at__isnull=True)
                .order_by("updated_at")
                .first()
            )
            event = "recording"
        if item is None:
            item = (
                VideoRequest.objects.select_for_update(skip_locked=True)
                .select_related("student", "assigned_tutor")
                .filter(status=VideoRequest.Status.READY, ready_notification_sent_at__isnull=True)
                .order_by("video_ready_at", "updated_at")
                .first()
            )
            event = "ready"
        if item is None:
            return False

        if event == "confirmation":
            position = video_request_queue_position(item)
            eta_from, eta_to = video_request_eta(item)
            _send_video_request_message(
                item,
                subject=f"Amaris video request paid and queued — {item.ticket_number}",
                heading="Your requested video is in the paid queue",
                body_lines=[
                    f"Ticket: {item.ticket_number}",
                    f"Package: {item.get_request_type_display()}",
                    f"Topic: {item.topic}",
                    f"Queue position: {position}",
                    f"Estimated ready window: {eta_from} to {eta_to}",
                    "The estimate is a planning range, not a delivery guarantee.",
                    "Track progress securely from your Amaris dashboard.",
                ],
                attach_invoice=True,
            )
            item.confirmation_sent_at = timezone.now()
            item.save(update_fields=("confirmation_sent_at", "updated_at"))
        elif event == "position_one":
            _send_video_request_message(
                item,
                subject=f"Your Amaris video request is next — {item.ticket_number}",
                heading="Your video request is next in the queue",
                body_lines=[
                    f"Ticket: {item.ticket_number}",
                    f"Topic: {item.topic}",
                    "A tutor will begin the recording workflow when the current recording is complete.",
                ],
            )
            item.position_one_sent_at = timezone.now()
            item.save(update_fields=("position_one_sent_at", "updated_at"))
        elif event == "recording":
            _send_video_request_message(
                item,
                subject=f"Recording started — {item.ticket_number}",
                heading="Your requested lesson is being recorded",
                body_lines=[
                    f"Ticket: {item.ticket_number}",
                    f"Tutor: {item.tutor_display_name}",
                    f"Topic: {item.topic}",
                    "We will notify you after processing and quality review are complete.",
                ],
            )
            item.recording_sent_at = timezone.now()
            item.save(update_fields=("recording_sent_at", "updated_at"))
        else:
            _send_video_request_message(
                item,
                subject=f"Your Amaris video is ready — {item.ticket_number}",
                heading="Your requested video is ready",
                body_lines=[
                    f"Ticket: {item.ticket_number}",
                    f"Topic: {item.topic}",
                    "Sign in to your Amaris dashboard to watch it securely.",
                    "The video is assigned to your account and must not be shared.",
                ],
            )
            item.ready_notification_sent_at = timezone.now()
            item.save(update_fields=("ready_notification_sent_at", "updated_at"))
        return True


@shared_task(
    bind=True,
    ignore_result=True,
    autoretry_for=(OperationalError, InterfaceError, OSError, BotoCoreError, ClientError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 6},
)
def expire_unpaid_video_requests(_self) -> int:
    expired = list(
        VideoRequest.objects.filter(
            status=VideoRequest.Status.PENDING_PAYMENT,
            payment_expires_at__lte=timezone.now(),
        ).prefetch_related("documents")[:100]
    )
    storage = storages["student_private"]
    count = 0
    for item in expired:
        with transaction.atomic():
            locked = VideoRequest.objects.select_for_update().get(pk=item.pk)
            if locked.status != VideoRequest.Status.PENDING_PAYMENT or locked.payment_expires_at > timezone.now():
                continue
            # Payment callbacks lock this same row. Recheck before touching
            # storage so a verified payment cannot lose its supporting files.
            # Retain metadata if storage fails so the next task can retry.
            for document in locked.documents.all():
                storage.delete(document.storage_path)
            locked.documents.all().delete()
            locked.status = VideoRequest.Status.CANCELLED
            locked.save(update_fields=("status", "updated_at"))
            count += 1
    return count


@shared_task(bind=True, ignore_result=True, max_retries=6)
def archive_invoice_pdf_task(self, invoice_id: int) -> str:
    """Generate and archive one verified paid invoice in private Supabase Storage."""

    try:
        return archive_invoice_pdf(invoice_id)
    except Exception as exc:
        mark_invoice_archive_failure(invoice_id, exc)
        countdown = min(300, 2 ** min(self.request.retries + 1, 8))
        raise self.retry(exc=exc, countdown=countdown) from exc


@shared_task(bind=True, ignore_result=True)
def archive_missing_invoice_pdfs(_self) -> int:
    """Recovery sweep for verified invoices whose PDF was not archived yet."""

    invoice_ids = list(
        Invoice.objects.filter(
            payment__status="paid",
            payment__gateway_verified_at__isnull=False,
            pdf_storage_path="",
        )
        .order_by("issued_at")
        .values_list("pk", flat=True)[:100]
    )
    queued = 0
    for invoice_id in invoice_ids:
        try:
            archive_invoice_pdf_task.delay(invoice_id)
            queued += 1
        except Exception:
            continue
    return queued
