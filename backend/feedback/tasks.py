import json
import logging
from celery import shared_task
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
