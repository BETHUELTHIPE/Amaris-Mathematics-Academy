import json
import logging
from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.mail import send_mail
from django.utils import timezone
from content.models import SiteSettings
from .models import HappyForm

logger = logging.getLogger(__name__)

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, retry_kwargs={"max_retries": 6}, ignore_result=True)
def deliver_happy_form(self, form_id):
    form = HappyForm.objects.select_related("student").get(pk=form_id)
    if not settings.CMS_STORAGE_BUCKET_NAME:
        raise RuntimeError('Private CMS storage bucket is required for feedback archives.')
    if not form.archived_at:
        archive = {
            "id": str(form.pk), "student_email": form.student.email,
            "service": form.service, "service_reference": form.service_reference,
            "service_title": form.service_title, "tutor": form.tutor_name,
            "overall_rating": form.overall_rating, "tutor_rating": form.tutor_rating,
            "comments": form.comments, "created_at": form.created_at.isoformat(),
        }
        path = f"feedback-forms/{form.id}.json"
        if not default_storage.exists(path):
            default_storage.save(path, ContentFile(json.dumps(archive, ensure_ascii=False, indent=2).encode("utf-8")))
        form.archive_path = path
        form.archived_at = timezone.now()
        form.save(update_fields=["archive_path", "archived_at"])
    if not form.admin_emailed_at:
        site = SiteSettings.objects.first()
        if not site or not site.email:
            raise ValueError("Admin notification email is not configured in Site Settings.")
        subject = f"New Amaris happy form — {form.overall_rating}/5"
        body = (
            f"Student: {form.student.email}\nService: {form.service_title}\n"
            f"Tutor: {form.tutor_name or 'N/A'}\nOverall: {form.overall_rating}/5\n"
            f"Tutor rating: {str(form.tutor_rating) + '/5' if form.tutor_rating else 'N/A'}\n"
            f"Comments: {form.comments}\nReference: {form.service_reference}\n"
            f"Archive: {form.archive_path}"
        )
        sent = send_mail(subject, body, None, [site.email], fail_silently=False)
        if sent != 1:
            raise RuntimeError("Admin email not accepted by SMTP provider.")
        form.admin_emailed_at = timezone.now()
        form.save(update_fields=["admin_emailed_at"])


@shared_task(bind=True, autoretry_for=(OSError,), retry_backoff=True, retry_kwargs={"max_retries": 5}, ignore_result=True)
def notify_new_followup(self, followup_id):
    from .models import FeedbackFollowUp

    followup = FeedbackFollowUp.objects.select_related("feedback__student").get(pk=followup_id)
    site = SiteSettings.objects.first()
    if not site or not site.email:
        raise OSError("Administrator email is missing.")
    email = followup.feedback.student.email
    sent = send_mail(
        "Action required: unhappy student follow-up",
        (
            f"Student: {email}\n"
            f"Service: {followup.feedback.service_title}\n"
            f"Overall: {followup.feedback.overall_rating}/5\n"
            f"Tutor: {followup.feedback.tutor_rating or 'Not rated'}\n"
            f"Call deadline (South African time): {timezone.localtime(followup.due_at):%d %B %Y %H:%M SAST}\n"
            "Please review the follow-up task under Django Admin > Feedback forms."
        ),
        None,
        [site.email],
        fail_silently=False,
    )
    if sent != 1:
        raise OSError("SMTP did not accept follow-up alert.")


@shared_task(ignore_result=True)
def remind_due_followups():
    """Schedule in Celery Beat; retries can repeat SMTP if interrupted."""
    from .models import FeedbackFollowUp

    site = SiteSettings.objects.first()
    if not site or not site.email:
        raise OSError("Administrator email is missing.")
    for followup in FeedbackFollowUp.objects.filter(
        status=FeedbackFollowUp.Status.PENDING,
        due_at__lte=timezone.now(),
        reminder_sent_at__isnull=True,
    ).select_related("feedback__student")[:100]:
        with __import__("django").db.transaction.atomic():
            selected = FeedbackFollowUp.objects.select_for_update().get(pk=followup.pk)
            if selected.reminder_sent_at or selected.status != FeedbackFollowUp.Status.PENDING:
                continue
            sent = send_mail(
                "Due now: Call unhappy Amaris student",
                (
                    f"Student: {selected.feedback.student.email}\n"
                    f"Service: {selected.feedback.service_title}\n"
                    f"Deadline: {timezone.localtime(selected.due_at):%d %B %Y %H:%M SAST}\n"
                    "Open Django Admin > Feedback forms > Student follow-ups."
                ),
                None,
                [site.email],
                fail_silently=False,
            )
            if sent != 1:
                raise OSError("SMTP did not accept due-date reminder.")
            selected.reminder_sent_at = timezone.now()
            selected.save(update_fields=["reminder_sent_at", "updated_at"])
