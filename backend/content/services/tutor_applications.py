"""Durable acknowledgement delivery; SMTP failures never discard an application."""

from datetime import timedelta
from html import escape

from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.utils import timezone

from content.models import TutorApplication


def deliver_application_acknowledgement(application_id=None) -> int:
    with transaction.atomic():
        pending = TutorApplication.objects.select_for_update(skip_locked=True).filter(
            acknowledgement_sent_at__isnull=True, acknowledgement_next_attempt_at__lte=timezone.now()
        )
        if application_id is not None:
            pending = pending.filter(pk=application_id)
        application = pending.order_by("submitted_at").first()
        if application is None:
            return 0
        application.acknowledgement_attempts += 1
        reference = application.reference
        text = (
            f"Dear {application.full_name},\n\n"
            "Thank you for applying to become an Amaris tutor. We have received your application "
            "and qualification documents.\n\n"
            f"Application reference: {reference}\n\n"
            "Our recruitment team will review your qualifications and teaching experience and contact you "
            "using your registered email if further information or an interview is needed. "
            "This acknowledgement is not an offer or approval to teach. "
            "Sign in on the Amaris website and open Become a tutor to view your application status.\n\n"
            "Amaris Mathematics Academy"
        )
        message = EmailMultiAlternatives(
            subject=f"Amaris tutor application received — {reference}", body=text, to=[application.email]
        )
        message.attach_alternative(
            f"<h1>Application received</h1><p>Dear {escape(application.full_name)},</p>"
            f"<p>Thank you for applying to become an Amaris tutor.</p><p>Reference: <strong>{reference}</strong></p>"
            "<p>We have received your application and qualification documents. Our recruitment team will review "
            "them and contact you if further information or an interview is needed.</p>"
            "<p>This acknowledgement is not an offer or approval to teach. Sign in on the Amaris website "
            "and open Become a tutor to view your application status.</p><p>Amaris Mathematics Academy</p>",
            "text/html",
        )
        try:
            if message.send(fail_silently=False) != 1:
                raise OSError("Mail backend did not accept the acknowledgement.")
        except Exception as exc:
            application.acknowledgement_error = type(exc).__name__[:120]
            application.acknowledgement_next_attempt_at = timezone.now() + timedelta(
                seconds=min(3600, 60 * 2 ** min(application.acknowledgement_attempts, 6))
            )
        else:
            application.acknowledgement_sent_at = timezone.now()
            application.acknowledgement_error = ""
        application.save(
            update_fields=[
                "acknowledgement_attempts",
                "acknowledgement_error",
                "acknowledgement_next_attempt_at",
                "acknowledgement_sent_at",
            ]
        )
        return int(application.acknowledgement_sent_at is not None)
