from datetime import timedelta

from celery import shared_task
from django.apps import apps
from django.conf import settings
from django.core.mail import send_mail
from django.db import models, transaction
from django.db.utils import InterfaceError, OperationalError
from django.utils import timezone

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


def _notification_body(outbox: NotificationOutbox) -> tuple[str, str]:
    payload = outbox.payload if isinstance(outbox.payload, dict) else {}
    course = str(payload.get("course", "your mathematics course")).strip()
    invoice = str(payload.get("invoice_number", "")).strip()
    ticket = str(payload.get("ticket_number", "")).strip()
    reference = str(payload.get("payment_reference", outbox.payment.reference)).strip()

    subject = f"Amaris payment confirmed — {course}"[:180]
    lines = [
        "Your payment has been verified and your Amaris course access is active.",
        "",
        f"Course: {course}",
        f"Payment reference: {reference}",
    ]
    if invoice:
        lines.append(f"Invoice: {invoice}")
    if ticket:
        lines.append(f"Service ticket: {ticket}")
    lines.extend(
        [
            "",
            "Sign in to your Amaris dashboard to continue learning and access your documents.",
            "",
            "Do not reply with passwords, one-time codes, or card details.",
        ]
    )
    return subject, "\n".join(lines)


@shared_task(
    bind=True,
    ignore_result=True,
    autoretry_for=(OperationalError, InterfaceError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    retry_kwargs={"max_retries": 6},
)
def deliver_notification_outbox(_self, outbox_id: int) -> bool:
    """Deliver one transactional message without logging recipient or payload data."""

    with transaction.atomic():
        outbox = (
            NotificationOutbox.objects.select_for_update()
            .select_related("payment", "payment__course")
            .filter(pk=outbox_id)
            .first()
        )
        if outbox is None or outbox.status == NotificationOutbox.Status.SENT:
            return True
        if outbox.attempts >= 5:
            return False

        outbox.status = NotificationOutbox.Status.SENDING
        outbox.attempts += 1
        outbox.last_error_code = ""
        outbox.save(update_fields=["status", "attempts", "last_error_code", "updated_at"])
        destination = outbox.destination
        subject, body = _notification_body(outbox)

    try:
        sent = send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[destination],
            fail_silently=False,
        )
        if sent != 1:
            raise RuntimeError("smtp_send_count_mismatch")
    except Exception as exc:  # noqa: BLE001 - convert provider detail to a non-sensitive code.
        with transaction.atomic():
            failed = NotificationOutbox.objects.select_for_update().filter(pk=outbox_id).first()
            if failed is not None and failed.status != NotificationOutbox.Status.SENT:
                failed.status = NotificationOutbox.Status.FAILED
                failed.last_error_code = exc.__class__.__name__[:80]
                failed.save(update_fields=["status", "last_error_code", "updated_at"])
        return False

    with transaction.atomic():
        delivered = NotificationOutbox.objects.select_for_update().filter(pk=outbox_id).first()
        if delivered is not None:
            delivered.status = NotificationOutbox.Status.SENT
            delivered.last_error_code = ""
            delivered.save(update_fields=["status", "last_error_code", "updated_at"])
    return True


@shared_task(bind=True, ignore_result=True)
def deliver_queued_notifications(_self) -> int:
    """Queue bounded notification retries; stale sending rows can recover after a worker crash."""

    stale_before = timezone.now() - timedelta(minutes=10)
    ids = list(
        NotificationOutbox.objects.filter(attempts__lt=5)
        .filter(
            models.Q(status__in=[NotificationOutbox.Status.QUEUED, NotificationOutbox.Status.FAILED])
            | models.Q(status=NotificationOutbox.Status.SENDING, updated_at__lt=stale_before)
        )
        .order_by("created_at")
        .values_list("id", flat=True)[:100]
    )
    for outbox_id in ids:
        deliver_notification_outbox.apply_async(args=[outbox_id], queue="notifications")
    return len(ids)
