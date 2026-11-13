"""Private personnel archive and conservative, idempotent Admin delivery."""

import hashlib
import json
import logging
from datetime import timedelta
from smtplib import SMTPAuthenticationError, SMTPConnectError, SMTPDataError, SMTPRecipientsRefused, SMTPSenderRefused
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from content.models import SiteSettings
from content.services.branded_email import DEFAULT_EMAIL, apply_letterhead
from content.services.tutor_personnel_pdf import form_lines, render_personnel_form
from content.services.tutor_video_uploads import UploadConflict, approved_tutor
from content.tutor_personnel_models import TutorPersonnelForm

logger = logging.getLogger(__name__)


def admin_recipient():
    site = SiteSettings.objects.first()
    recipient = settings.TUTOR_PERSONNEL_ADMIN_EMAIL or (site.email if site and site.email else DEFAULT_EMAIL)
    validate_email(recipient)
    return recipient


def submit_form(*, tutor, key, values):
    fingerprint = hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()
    saved = ""
    storage = TutorPersonnelForm._meta.get_field("pdf").storage
    try:
        with transaction.atomic():
            tutor = get_user_model().objects.select_for_update().get(pk=tutor.pk)
            if not approved_tutor(tutor):
                raise ValidationError("Approved tutor access is required.")
            prior = TutorPersonnelForm.objects.filter(tutor=tutor, idempotency_key=key).first()
            if prior:
                if prior.fingerprint != fingerprint:
                    raise UploadConflict("This submission key was already used for different form details.")
                return prior, False
            payload = {name: str(value) for name, value in values.items()}
            payload.update(
                tutor_name=tutor.get_full_name().strip() or tutor.get_username(),
                tutor_email=tutor.email,
                submitted_at=timezone.now()
                .astimezone(ZoneInfo("Africa/Johannesburg"))
                .strftime("%d %B %Y at %H:%M:%S SAST (UTC+2)"),
            )
            if values["kind"] == "leave":
                payload["calendar_days"] = str((values["end_date"] - values["start_date"]).days + 1)
                payload["leave_type_label"] = TutorPersonnelForm.LeaveType(values["leave_type"]).label
            item = TutorPersonnelForm(
                tutor=tutor,
                kind=values["kind"],
                idempotency_key=key,
                fingerprint=fingerprint,
                payload=payload,
                recipient=admin_recipient(),
            )
            document = render_personnel_form(item)
            saved = storage.save(f"tutor-personnel/{tutor.pk}/{item.pk}/{item.kind}.pdf", ContentFile(document))
            item.pdf, item.pdf_sha256 = saved, hashlib.sha256(document).hexdigest()
            item.full_clean()
            item.save()
            return item, True
    except Exception:
        if saved:
            try:
                storage.delete(saved)
            except Exception:
                logger.warning("tutor_personnel_private_orphan_cleanup_pending")
        raise


def archived_pdf(item):
    with item.pdf.open("rb") as source:
        document = source.read(1024 * 1024 + 1)
    if len(document) > 1024 * 1024 or hashlib.sha256(document).hexdigest() != item.pdf_sha256:
        raise ValidationError("The saved form needs archive review. Please contact the academy.")
    return document


def _failed(item, *, known_rejected, code):
    retry = known_rejected and item.attempts < 5
    TutorPersonnelForm.objects.filter(pk=item.pk, delivery_status="sending").update(
        delivery_status="queued" if retry else "review",
        error_code=code,
        next_attempt_at=timezone.now() + timedelta(minutes=2**item.attempts) if retry else None,
    )


def deliver_form(item_id):
    with transaction.atomic():
        item = TutorPersonnelForm.objects.select_for_update().get(pk=item_id)
        if item.delivery_status != "queued" or (item.next_attempt_at and item.next_attempt_at > timezone.now()):
            return 0
        if item.recipient != admin_recipient():
            item.delivery_status, item.error_code = "review", "admin_recipient_changed"
            item.save(update_fields=["delivery_status", "error_code", "updated_at"])
            return 0
        try:
            document = archived_pdf(item)
        except (ValidationError, FileNotFoundError):
            item.delivery_status, item.error_code = "review", "archive_integrity_review"
            item.save(update_fields=["delivery_status", "error_code", "updated_at"])
            return 0
        lines = ["A tutor submitted the attached confidential form. Review it in Django Admin."]
        lines += [f"{label}: {value}" for label, value in form_lines(item)]
        lines += [
            f"Form reference: {item.pk}",
            "The PDF records the original submission. Current review status is available in Django Admin.",
        ]
        message = EmailMultiAlternatives(
            subject=f"Amaris {item.get_kind_display()} - {item.pk}",
            body="\n\n".join(lines),
            to=[item.recipient],
            headers={"Message-ID": f"<tutor-form-{item.pk}@amaris.academy>"},
        )
        message.attach(f"amaris-{item.kind}-{item.pk}.pdf", document, "application/pdf")
        apply_letterhead(message, item.get_kind_display(), lines, reference=str(item.pk))
        item.delivery_status, item.sending_at = "sending", timezone.now()
        item.attempts += 1
        item.save(update_fields=["delivery_status", "sending_at", "attempts", "updated_at"])
    try:
        sent = message.send(fail_silently=False)
    except (SMTPAuthenticationError, SMTPConnectError, SMTPDataError, SMTPRecipientsRefused, SMTPSenderRefused):
        _failed(item, known_rejected=True, code="smtp_rejected")
        return 0
    except Exception:
        _failed(item, known_rejected=False, code="smtp_outcome_unknown")
        return 0
    if sent != 1:
        _failed(item, known_rejected=True, code="mail_not_accepted")
        return 0
    TutorPersonnelForm.objects.filter(pk=item.pk, delivery_status="sending").update(
        delivery_status="sent", sent_at=timezone.now(), error_code=""
    )
    return 1
