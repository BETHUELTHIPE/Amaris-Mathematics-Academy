import hashlib
import logging
from datetime import date, time, timedelta
from smtplib import SMTPAuthenticationError, SMTPConnectError, SMTPDataError, SMTPRecipientsRefused, SMTPSenderRefused

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.db import connection, transaction
from django.utils import timezone

from content.models import SiteSettings
from content.performance_models import PerformanceDigest, PerformanceSchedule
from content.services.branded_email import DEFAULT_EMAIL, apply_letterhead
from content.services.performance_metrics import SAST, build_snapshot, report_sections
from content.services.performance_pdf import render_performance_pdf

logger = logging.getLogger(__name__)


def admin_recipient():
    site = SiteSettings.objects.first()
    recipient = settings.ADMIN_PERFORMANCE_ADMIN_EMAIL or (site.email if site and site.email else DEFAULT_EMAIL)
    validate_email(recipient)
    return recipient


def due_period(anchor, now):
    local = now.astimezone(SAST)
    count = (local.date() - anchor).days // 14
    if count < 1:
        return None
    end = anchor + timedelta(days=count * 14)
    if local.date() == end and local.time() < time(9):
        count -= 1
        end -= timedelta(days=14)
    return (end - timedelta(days=14), end) if count >= 1 else None


def generate_due_report():
    if not settings.ADMIN_PERFORMANCE_REPORTS_ENABLED:
        return None, False
    now, stored = timezone.now(), ""
    storage = PerformanceDigest._meta.get_field("pdf").storage
    outer_transaction = connection.in_atomic_block
    try:
        with transaction.atomic():
            if connection.vendor == "postgresql" and not outer_transaction:
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            mode = settings.ADMIN_PERFORMANCE_PAYMENT_MODE
            anchor = (
                date.fromisoformat(settings.ADMIN_PERFORMANCE_START_DATE)
                if settings.ADMIN_PERFORMANCE_START_DATE
                else now.astimezone(SAST).date()
            )
            PerformanceSchedule.objects.get_or_create(payment_mode=mode, defaults={"anchor_date": anchor})
            schedule = PerformanceSchedule.objects.select_for_update().get(payment_mode=mode)
            period = due_period(schedule.anchor_date, now)
            if period is None:
                return None, False
            start, end = period
            prior = PerformanceDigest.objects.filter(payment_mode=mode, period_start=start).first()
            if prior:
                return prior, False
            item = PerformanceDigest(payment_mode=mode, period_start=start, period_end=end, recipient=admin_recipient())
            item.snapshot = build_snapshot(start, end, mode)
            earlier = PerformanceDigest.objects.filter(payment_mode=mode, period_start__lt=start).count()
            item.snapshot["missing_periods"] = max(0, (start - schedule.anchor_date).days // 14 - earlier)
            document = render_performance_pdf(item.snapshot, str(item.pk))
            stored = storage.save(f"admin-performance/{mode}/{start}/{item.pk}.pdf", ContentFile(document))
            item.pdf, item.pdf_sha256 = stored, hashlib.sha256(document).hexdigest()
            item.full_clean()
            item.save()
            return item, True
    except Exception:
        if stored:
            try:
                storage.delete(stored)
            except Exception:
                logger.warning("performance_report_private_orphan_cleanup_pending")
        raise


def archived_pdf(item):
    with item.pdf.open("rb") as source:
        document = source.read(1024 * 1024 + 1)
    if len(document) > 1024 * 1024 or hashlib.sha256(document).hexdigest() != item.pdf_sha256:
        raise ValidationError("The performance archive needs review.")
    return document


def _failed(item, *, known_rejected, code):
    retry = known_rejected and item.attempts < 5
    PerformanceDigest.objects.filter(pk=item.pk, delivery_status="sending").update(
        delivery_status="queued" if retry else "review",
        error_code=code,
        next_attempt_at=timezone.now() + timedelta(minutes=2**item.attempts) if retry else None,
    )


def deliver_report(item_id):
    if not settings.ADMIN_PERFORMANCE_REPORTS_ENABLED:
        return 0
    with transaction.atomic():
        item = PerformanceDigest.objects.select_for_update().get(pk=item_id)
        if item.delivery_status != "queued" or (item.next_attempt_at and item.next_attempt_at > timezone.now()):
            return 0
        if item.recipient != admin_recipient() or item.payment_mode != settings.ADMIN_PERFORMANCE_PAYMENT_MODE:
            item.delivery_status, item.error_code = "review", "recipient_or_mode_changed"
            item.save(update_fields=["delivery_status", "error_code", "updated_at"])
            return 0
        try:
            document = archived_pdf(item)
        except (ValidationError, FileNotFoundError):
            item.delivery_status, item.error_code = "review", "archive_integrity_review"
            item.save(update_fields=["delivery_status", "error_code", "updated_at"])
            return 0
        lines = []
        for heading, content in report_sections(item.snapshot):
            lines.extend([heading.upper(), *content])
        message = EmailMultiAlternatives(
            subject=(
                f"Amaris {item.payment_mode.upper()} performance | "
                f"{item.period_start} to {item.snapshot['last_day']}"
            ),
            body="\n\n".join(lines),
            to=[item.recipient],
            headers={"Message-ID": f"<performance-{item.pk}@amaris.academy>"},
        )
        message.attach(f"amaris-performance-{item.period_start}.pdf", document, "application/pdf")
        apply_letterhead(message, "Your fortnightly academy performance review", lines, reference=str(item.pk))
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
        _failed(item, known_rejected=sent == 0, code="mail_not_accepted" if sent == 0 else "mail_outcome_unknown")
        return 0
    PerformanceDigest.objects.filter(pk=item.pk, delivery_status="sending").update(
        delivery_status="sent", sent_at=timezone.now(), error_code=""
    )
    return 1
