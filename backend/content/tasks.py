from smtplib import SMTPException
from urllib.parse import urljoin

from celery import shared_task
from django.apps import apps
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.db.utils import InterfaceError, OperationalError
from django.template.loader import render_to_string
from django.utils import timezone
from openai import OpenAIError

from amaris_cms.incidents import dispatch_incident_to_github
from content.models import ContactEnquiry
from content.services.enquiry_autoreply import (
    build_email_connection,
    build_enquiry_reply_context,
    contact_auto_reply_enabled,
    default_from_email,
    generate_enquiry_ai_reply,
)
from content.services.reconciliation import reconcile_verified_payments


def _build_letterhead_context(context: dict) -> dict[str, str]:
    """Freeze the current company letterhead values into the outgoing message context."""

    site = context.get("site")
    website_url = (context.get("website_url") or "").rstrip("/")
    logo_url = ""

    if site and site.logo:
        try:
            logo_url = site.logo.url
        except ValueError:
            logo_url = ""

    if logo_url and not logo_url.startswith(("http://", "https://", "cid:", "data:")):
        logo_url = urljoin(f"{website_url}/", logo_url.lstrip("/")) if website_url else logo_url
    elif not logo_url and website_url:
        logo_url = urljoin(f"{website_url}/", "brand/amaris-academy-icon-192.png")

    return {
        "site_name": context.get("site_name") or "Amaris Mathematics Academy",
        "logo_url": logo_url,
        "managing_director": site.managing_director if site else "",
        "phone": site.phone if site else "",
        "email": site.email if site else "",
        "website_url": website_url,
        "address": site.address if site else "",
        "business_hours": site.business_hours if site else "",
    }


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
    autoretry_for=(OSError, RuntimeError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    retry_kwargs={"max_retries": 6},
)
def dispatch_production_incident(_self, incident: dict) -> dict[str, str]:
    """Forward only a pre-sanitized incident to the GitHub response workflow."""

    dispatch_incident_to_github(incident)
    return {"status": "dispatched"}


@shared_task(bind=True, ignore_result=True, max_retries=5)
def send_contact_enquiry_auto_reply(self, enquiry_id: int) -> dict[str, str]:
    """Generate a grounded GPT reply and email it to one contact-form student.

    OpenAI receives the enquiry subject/message plus selected published website
    content; the dedicated email and phone fields are not included in the model
    prompt. OpenAI/SMTP failures retry with exponential backoff. A cache lock
    prevents concurrent duplicate sends. The rendered text and HTML versions
    both receive the same frozen company letterhead context.
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
        context["ai_reply"] = generate_enquiry_ai_reply(enquiry, context)
        context["letterhead"] = _build_letterhead_context(context)
        site = context["site"]
        sender = default_from_email(site)
        if not sender:
            raise RuntimeError("No sender email is configured for contact auto-replies.")

        subject = f"Re: {enquiry.subject} — {context['site_name']}"
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
    except (OpenAIError, SMTPException, OSError) as exc:
        cache.delete(lock_key)
        countdown = min(300, 5 * (2**self.request.retries))
        raise self.retry(exc=exc, countdown=countdown) from exc
    finally:
        cache.delete(lock_key)
