"""Celery Beat orchestration and independent, retry-safe tutor/admin email dispatch."""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings
from django.core.files.storage import storages
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.utils import timezone

from content.services.tutor_statements import archive_statement, issue_due_statements
from content.tutor_finance_models import TutorActivityStatement

logger = logging.getLogger(__name__)


@shared_task(ignore_result=True)
def create_due_tutor_statements():
    """Runs daily; exactly one 30-day non-overlapping cycle per tutor."""
    return issue_due_statements(limit=500)


def _render_email(statement, *, recipient_kind):
    report = statement.snapshot
    person = "Tutor" if recipient_kind == "tutor" else "Academy Administration"
    title = f"Amaris | 30-day tutor statement | {statement.report_number}"
    plain = (
        f"Dear {person},\n\n"
        f"Attached is the confidential Amaris tutor activity and earnings statement for "
        f"{report['tutor_name']}, covering {report['period_start']} to "
        f"{report['period_end_exclusive']} (exclusive).\n\n"
        f"Unique students served: {report['unique_students']}\n"
        f"Completed live classes: {report['sessions_taught']}\n"
        f"Teaching hours: {report['hours_taught']}\n"
        f"Paid video requests: {report['video_requests']}\n"
        f"Videos ready: {report['videos_delivered']}\n"
        f"Verified gross sales: R {report['gross_verified']}\n"
        f"Tutor earnings accrued: R {report['tutor_share']}\n"
        f"Eligible tutor earnings: R {report['ready_earnings']}\n"
        f"Held tutor earnings: R {report['held_earnings']}\n"
        f"Provider-confirmed payouts during period: R {report['confirmed_payouts_in_period']}\n\n"
        "This report is not a remittance advice or proof of bank payment. "
        "Only verified payout references count as paid. "
        "Contact Amaris administration with the statement reference for any discrepancy.\n\n"
        "Amaris Mathematics Academy"
    )
    return title, plain


def send_statement_recipient(statement_id: int, recipient_kind: str):
    """Commit each recipient independently so admin retries never re-email tutors.

    A database lock prevents parallel workers from emailing the same role twice.
    SMTP has no true exactly-once acknowledgement; process death after SMTP but
    before DB commit can require reconciliation before an automatic retry.
    """
    if recipient_kind not in ("tutor", "admin"):
        raise ValueError("Unrecognised statement recipient")
    with transaction.atomic():
        statement = TutorActivityStatement.objects.select_for_update().select_related("tutor").get(pk=statement_id)
        field = "tutor_emailed_at" if recipient_kind == "tutor" else "admin_emailed_at"
        if getattr(statement, field):
            return False
        if not statement.pdf_storage_path or not statement.pdf_sha256:
            raise RuntimeError("Cannot email a statement before private archive")

        if recipient_kind == "tutor":
            recipient = statement.tutor.email.strip()
        else:
            recipient = getattr(settings, "TUTOR_STATEMENT_ADMIN_EMAIL", "").strip()
        if not recipient:
            raise RuntimeError("A tutor or admin statement recipient is not configured")

        with storages["default"].open(statement.pdf_storage_path, "rb") as source:
            pdf = source.read()
        import hashlib

        if hashlib.sha256(pdf).hexdigest() != statement.pdf_sha256 or not pdf.startswith(b"%PDF"):
            raise RuntimeError("Private statement archive integrity verification failed")

        subject, plain = _render_email(statement, recipient_kind=recipient_kind)
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient],
            headers={"X-Amaris-Statement": statement.report_number},
        )
        email.attach(f"{statement.report_number}.pdf", pdf, "application/pdf")
        if email.send(fail_silently=False) != 1:
            raise OSError("Statement email provider did not accept this message")

        setattr(statement, field, timezone.now())
        updates = [field, "updated_at"]
        if statement.tutor_emailed_at and statement.admin_emailed_at:
            statement.state = TutorActivityStatement.State.DELIVERED
            updates.append("state")
        statement.save(update_fields=updates)
        return True


@shared_task(
    ignore_result=True, bind=True, autoretry_for=(OSError,), retry_backoff=True, retry_kwargs={"max_retries": 5}
)
def deliver_due_tutor_statements(_task):
    """Beat sweep with bounded work, private PDF archive and separate role delivery."""
    pending = list(
        TutorActivityStatement.objects.exclude(state=TutorActivityStatement.State.DELIVERED)
        .order_by("period_end", "pk")
        .values_list("pk", flat=True)[:50]
    )
    completed = 0
    for statement_id in pending:
        try:
            with transaction.atomic():
                statement = TutorActivityStatement.objects.select_for_update().get(pk=statement_id)
                if not statement.pdf_storage_path:
                    archive_statement(statement)
            if send_statement_recipient(statement_id, "tutor"):
                completed += 1
            if send_statement_recipient(statement_id, "admin"):
                completed += 1
        except Exception:
            # Do not dump recipient, PDF contents or private object keys into logs.
            logger.exception("tutor_statement_delivery_failed", extra={"statement_id": statement_id})
            continue
    return completed
