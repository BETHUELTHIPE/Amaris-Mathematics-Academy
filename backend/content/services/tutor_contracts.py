"""Save-first tutor contract archive, countersignature and Admin delivery."""

import hashlib
import json
import logging
from datetime import timedelta
from decimal import Decimal
from smtplib import SMTPAuthenticationError, SMTPConnectError, SMTPDataError, SMTPRecipientsRefused, SMTPSenderRefused
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from content.models import SiteSettings
from content.services.branded_email import DEFAULT_EMAIL, apply_letterhead
from content.services.tutor_contract_pdf import contract_summary_lines, render_tutor_contract
from content.services.tutor_video_uploads import UploadConflict, approved_tutor
from content.tutor_contract_models import TutorEmploymentContract
from content.tutor_finance_models import TutorContract

logger = logging.getLogger(__name__)
TERMS_VERSION = "ZA-TUTOR-EMPLOYMENT-2026-02"
STATUTORY_HOURLY_FLOOR = Decimal("30.23")
EMPLOYMENT_TUTOR_PERCENT = Decimal("40.00")
MAX_PDF_BYTES = 2 * 1024 * 1024


class ContractInputError(Exception):
    """Safe tutor-facing validation message."""


def admin_recipient():
    site = SiteSettings.objects.first()
    recipient = settings.TUTOR_PERSONNEL_ADMIN_EMAIL or (site.email if site and site.email else DEFAULT_EMAIL)
    validate_email(recipient)
    return recipient


def current_service_terms(tutor):
    now = timezone.now()
    rows = list(
        TutorContract.objects.filter(tutor=tutor, is_active=True, effective_from__lte=now)
        .filter(Q(effective_until__isnull=True) | Q(effective_until__gt=now))
        .order_by("service", "-effective_from")
    )
    by_service = {}
    for row in rows:
        if row.service in by_service:
            raise ContractInputError("The Academy must resolve overlapping remuneration terms before signing.")
        if row.tutor_percent != EMPLOYMENT_TUTOR_PERCENT:
            raise ContractInputError(
                "The Academy must configure remuneration as 60% Admin / 40% Tutor before signing. "
                "Existing agreements and earned amounts are not changed automatically."
            )
        by_service[row.service] = row
    if TutorContract.Service.LIVE_CLASS not in by_service:
        raise ContractInputError("The Academy must configure your online-class remuneration before signing.")
    return [
        {
            "service": row.service,
            "service_label": row.get_service_display(),
            "tutor_percent": f"{row.tutor_percent:.2f}",
            "academy_percent": f"{Decimal('100.00') - row.tutor_percent:.2f}",
            "contract_reference": row.contract_reference,
            "effective_from": row.effective_from.isoformat(),
            "effective_until": row.effective_until.isoformat() if row.effective_until else None,
        }
        for row in by_service.values()
    ]


def offer_summary(tutor):
    try:
        terms = current_service_terms(tutor)
    except ContractInputError as exc:
        return {"available": False, "detail": str(exc), "service_terms": []}
    return {
        "available": True,
        "detail": "Review these employer-configured terms before signing.",
        "terms_version": TERMS_VERSION,
        "statutory_hourly_floor": f"{STATUTORY_HOURLY_FLOOR:.2f}",
        "currency": "ZAR",
        "pay_frequency": "Monthly; no later than seven days after the pay period",
        "service_terms": terms,
    }


def submit_contract(*, tutor, key, values):
    fingerprint = hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()
    saved = ""
    storage = TutorEmploymentContract._meta.get_field("employee_pdf").storage
    try:
        with transaction.atomic():
            tutor = get_user_model().objects.select_for_update().get(pk=tutor.pk)
            if not approved_tutor(tutor):
                raise ValidationError("Approved tutor access is required.")
            prior = TutorEmploymentContract.objects.filter(tutor=tutor, idempotency_key=key).first()
            if prior:
                if prior.fingerprint != fingerprint:
                    raise UploadConflict("This submission key was already used for different contract details.")
                return prior, False
            if values["preferred_start_date"] < timezone.localdate():
                raise ContractInputError("The preferred commencement date must be today or later.")
            service_terms = current_service_terms(tutor)
            payload = {
                name: ([str(v) for v in value] if isinstance(value, list) else str(value))
                for name, value in values.items()
            }
            payload.update(
                tutor_name=tutor.get_full_name().strip() or tutor.get_username(),
                tutor_email=tutor.email,
                submitted_at=timezone.now()
                .astimezone(ZoneInfo("Africa/Johannesburg"))
                .strftime("%d %B %Y at %H:%M:%S SAST (UTC+2)"),
            )
            item = TutorEmploymentContract(
                tutor=tutor,
                idempotency_key=key,
                fingerprint=fingerprint,
                terms_version=TERMS_VERSION,
                payload=payload,
                service_terms=service_terms,
                statutory_hourly_floor=STATUTORY_HOURLY_FLOOR,
                recipient=admin_recipient(),
            )
            document = render_tutor_contract(item)
            saved = storage.save(f"tutor-contracts/{tutor.pk}/{item.pk}/tutor-signed.pdf", ContentFile(document))
            item.employee_pdf, item.employee_pdf_sha256 = saved, hashlib.sha256(document).hexdigest()
            item.full_clean()
            item.save()
            return item, True
    except Exception:
        if saved:
            try:
                storage.delete(saved)
            except Exception:
                logger.warning("tutor_contract_private_orphan_cleanup_pending")
        raise


def _verified_file(file_field, digest):
    with file_field.open("rb") as source:
        document = source.read(MAX_PDF_BYTES + 1)
    if len(document) > MAX_PDF_BYTES or hashlib.sha256(document).hexdigest() != digest:
        raise ValidationError("The saved contract needs archive review. Please contact the academy.")
    return document


def archived_contract_pdf(item):
    if item.status == item.Status.ACCEPTED and item.executed_pdf and item.executed_pdf_sha256:
        return _verified_file(item.executed_pdf, item.executed_pdf_sha256)
    return _verified_file(item.employee_pdf, item.employee_pdf_sha256)


def employee_signed_pdf(item):
    return _verified_file(item.employee_pdf, item.employee_pdf_sha256)


def countersign_contract(item, *, reviewer):
    if not reviewer.is_superuser:
        raise ValidationError("Only a Super User may countersign an employment contract.")
    prior = TutorEmploymentContract.objects.get(pk=item.pk)
    if prior.status != TutorEmploymentContract.Status.SUBMITTED:
        raise ValidationError("A final contract decision cannot be changed online.")
    item.reviewed_by, item.reviewed_at = reviewer, timezone.now()
    item.full_clean()
    saved = ""
    storage = TutorEmploymentContract._meta.get_field("executed_pdf").storage
    try:
        with transaction.atomic():
            locked = TutorEmploymentContract.objects.select_for_update().get(pk=item.pk)
            if locked.status != TutorEmploymentContract.Status.SUBMITTED:
                raise ValidationError("This contract was already reviewed.")
            document = render_tutor_contract(item, executed=True)
            saved = storage.save(
                f"tutor-contracts/{item.tutor_id}/{item.pk}/executed.pdf", ContentFile(document)
            )
            item.executed_pdf = saved
            item.executed_pdf_sha256 = hashlib.sha256(document).hexdigest()
            item.save(
                update_fields=[
                    "status",
                    "review_notes",
                    "employer_signature_name",
                    "effective_date",
                    "reviewed_by",
                    "reviewed_at",
                    "executed_pdf",
                    "executed_pdf_sha256",
                    "updated_at",
                ]
            )
    except Exception:
        if saved:
            try:
                storage.delete(saved)
            except Exception:
                logger.warning("tutor_executed_contract_orphan_cleanup_pending")
        raise


def decline_contract(item, *, reviewer):
    if not reviewer.is_superuser:
        raise ValidationError("Only a Super User may decide an employment contract.")
    with transaction.atomic():
        locked = TutorEmploymentContract.objects.select_for_update().get(pk=item.pk)
        if locked.status != TutorEmploymentContract.Status.SUBMITTED:
            raise ValidationError("A final contract decision cannot be changed online.")
        item.reviewed_by, item.reviewed_at = reviewer, timezone.now()
        item.full_clean()
        item.save(update_fields=["status", "review_notes", "reviewed_by", "reviewed_at", "updated_at"])


def _failed(item, *, known_rejected, code):
    retry = known_rejected and item.attempts < 5
    TutorEmploymentContract.objects.filter(pk=item.pk, delivery_status="sending").update(
        delivery_status="queued" if retry else "review",
        error_code=code,
        next_attempt_at=timezone.now() + timedelta(minutes=2**item.attempts) if retry else None,
    )


def deliver_contract(item_id):
    with transaction.atomic():
        item = TutorEmploymentContract.objects.select_for_update().get(pk=item_id)
        if item.delivery_status != "queued" or (item.next_attempt_at and item.next_attempt_at > timezone.now()):
            return 0
        if item.recipient != admin_recipient():
            item.delivery_status, item.error_code = "review", "admin_recipient_changed"
            item.save(update_fields=["delivery_status", "error_code", "updated_at"])
            return 0
        try:
            document = employee_signed_pdf(item)
        except (ValidationError, FileNotFoundError):
            item.delivery_status, item.error_code = "review", "archive_integrity_review"
            item.save(update_fields=["delivery_status", "error_code", "updated_at"])
            return 0
        lines = [
            "A tutor signed the attached employment contract. Super User review and countersignature are required."
        ]
        lines += [f"{label}: {value}" for label, value in contract_summary_lines(item)]
        lines += [
            f"Contract reference: {item.pk}",
            "The attachment is the exact immutable PDF saved in the private tutor bucket.",
        ]
        message = EmailMultiAlternatives(
            subject=f"Tutor employment contract awaiting countersignature - {item.pk}",
            body="\n\n".join(lines),
            to=[item.recipient],
            headers={"Message-ID": f"<tutor-employment-{item.pk}@amaris.academy>"},
        )
        message.attach(f"amaris-tutor-employment-{item.pk}.pdf", document, "application/pdf")
        apply_letterhead(message, "Tutor employment contract", lines, reference=str(item.pk))
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
    TutorEmploymentContract.objects.filter(pk=item.pk, delivery_status="sending").update(
        delivery_status="sent", sent_at=timezone.now(), error_code=""
    )
    return 1
