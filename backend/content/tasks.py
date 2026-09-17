from smtplib import SMTPException

from celery import shared_task
from django.apps import apps
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.db.utils import InterfaceError, OperationalError
from django.template.loader import render_to_string
from django.utils import timezone

from content.models import ContactEnquiry
from content.services.enquiry_autoreply import (
    build_email_connection,
    build_enquiry_reply_context,
    contact_auto_reply_enabled,
    default_from_email,
)
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


@shared_task(bind=True, ignore_result=True, max_retries=5)
def send_contact_enquiry_auto_reply(self, enquiry_id: int) -> dict[str, str]:
    """Send one content-aware acknowledgement for a contact-form enquiry.

    The reply uses only published website content. SMTP failures retry with
    exponential backoff. A cache lock prevents concurrent duplicate sends.
    """

    if not contact_auto_reply_enabled():
        return {"status": "disabled"}

    sent_key = f"contact-auto-reply:sent:{enquiry_id}"
    lock_key = f"contact-auto-reply:lock:{enquiry_id}"
    if cache.get(sent_key):
        return {"status": "already-sent"}
    if not cache.add(lock_key, "1", timeout=300):
        return {"status": "already-processing"}

    try:
        enquiry = ContactEnquiry.objects.get(pk=enquiry_id)
        context = build_enquiry_reply_context(enquiry)
        site = context["site"]
        sender = default_from_email(site)
        if not sender:
            raise RuntimeError("No sender email is configured for contact auto-replies.")

        subject = f"We received your enquiry — {context['site_name']}"
        text_body = render_to_string("emails/contact_enquiry_auto_reply.txt", context)
        html_body = render_to_string("emails/contact_enquiry_auto_reply.html", context)
        reply_to = [site.email] if site and site.email else None

        message = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=sender,
            to=[enquiry.email],
            reply_to=reply_to,
            connection=build_email_connection(),
        )
        message.attach_alternative(html_body, "text/html")
        message.send(fail_silently=False)
        cache.set(sent_key, "1", timeout=60 * 60 * 24 * 30)
        return {"status": "sent"}
    except (SMTPException, OSError) as exc:
        cache.delete(lock_key)
        countdown = min(300, 5 * (2 ** self.request.retries))
        raise self.retry(exc=exc, countdown=countdown)
    finally:
        cache.delete(lock_key)
