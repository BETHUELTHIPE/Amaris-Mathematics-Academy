from celery import shared_task
from django.apps import apps
from django.core.mail import send_mail
from django.db import transaction
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
