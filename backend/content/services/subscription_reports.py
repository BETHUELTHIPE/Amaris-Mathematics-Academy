"""Freeze a private end-of-term learning record, then deliver it at most once automatically."""

import hashlib
from datetime import timedelta
from email.utils import make_msgid, parseaddr
from smtplib import SMTPAuthenticationError, SMTPConnectError, SMTPDataError, SMTPRecipientsRefused, SMTPSenderRefused
from typing import TypedDict
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from content.models import StudentRecord
from content.services.branded_email import apply_letterhead
from content.services.payments import _payfast_mode
from content.subscription_models import CurriculumSubscription
from content.subscription_report_models import SubscriptionReport, SubscriptionSession, SubscriptionStudyActivity

SAST = ZoneInfo("Africa/Johannesburg")
MAX_PDF_BYTES = 8 * 1024 * 1024


def date_label(value):
    return value.astimezone(SAST).strftime("%a %d %b %Y, %H:%M") if value else "Not recorded"


def duration_label(minutes):
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def eligible_subscriptions(now=None):
    now = now or timezone.now()
    return CurriculumSubscription.objects.filter(
        status="paid",
        gateway_verified_at__lte=now,
        gateway_mode=_payfast_mode(),
        student__is_active=True,
        starts_at__isnull=False,
        starts_at__lt=F("ends_at"),
        ends_at__lte=now,
    )


@transaction.atomic
def save_session(session, actor):
    """Attendance is explicitly confirmed by assigned tutors or authorised Django staff."""
    if not actor.is_active or not (
        actor.pk == session.tutor_id or actor.has_perm("content.change_subscriptionsession")
    ):
        raise ValidationError("Only the assigned tutor or authorised academy staff may record attendance.")
    if session.pk:
        current = SubscriptionSession.objects.select_for_update().get(pk=session.pk)
        if current.updated_at != session.updated_at:
            raise ValidationError("The session changed. Reload it before recording attendance.")
    get_user_model().objects.select_for_update().get(pk=session.tutor_id)
    StudentRecord.objects.select_for_update().get(pk=session.subscription.student_id)
    CurriculumSubscription.objects.select_for_update().get(pk=session.subscription_id)
    if session.status != "planned":
        if session.ends_at > timezone.now() and session.status != "cancelled":
            raise ValidationError("Attendance can only be confirmed after the session ends.")
        session.verified_by = actor
        session.verified_at = timezone.now()
    else:
        session.verified_by = None
        session.verified_at = None
    session.full_clean()
    session.save()
    return session


@transaction.atomic
def capture_study_activity(enrollment, kind="progress", lesson=None):
    if not enrollment.subscription_access_id:
        return
    sub = CurriculumSubscription.objects.select_for_update().get(pk=enrollment.subscription_access_id)
    now = timezone.now()
    if not (
        sub.student_id == enrollment.student_id
        and sub.status == "paid"
        and sub.gateway_verified_at
        and sub.gateway_mode == _payfast_mode()
        and sub.starts_at
        and sub.ends_at
        and sub.starts_at <= now < sub.ends_at
    ):
        return
    lesson_title = (
        lesson.title if lesson is not None else (enrollment.last_lesson.title if enrollment.last_lesson_id else "")
    )
    last = (
        SubscriptionStudyActivity.objects.filter(subscription=sub, enrollment=enrollment)
        .order_by("-occurred_at", "-pk")
        .first()
    )
    if (
        last
        and last.progress_percent == enrollment.progress_percent
        and last.lesson_title == lesson_title
        and (kind == "progress" or last.occurred_at.astimezone(SAST).date() == now.astimezone(SAST).date())
    ):
        return  # Playback heartbeats are not new learning milestones or attended hours.
    SubscriptionStudyActivity.objects.create(
        subscription=sub,
        enrollment=enrollment,
        occurred_at=now,
        kind=kind,
        course_title=enrollment.course.title,
        lesson_title=lesson_title,
        progress_percent=enrollment.progress_percent,
    )


class WeekSummary(TypedDict):
    week: str
    scheduled_minutes: int
    attended_minutes: int


def report_snapshot(sub, report_id):
    rows = []
    weeks: dict[str, WeekSummary] = {}
    counts = {key: 0 for key in SubscriptionSession.Status.values}
    attended = scheduled = 0
    for item in sub.sessions.select_related("tutor").filter(starts_at__gte=sub.starts_at, ends_at__lte=sub.ends_at):
        status = item.status if item.verified_at or item.status in {"planned", "cancelled"} else "planned"
        minutes = item.attended_minutes if status in {"attended", "partial"} else 0
        counts[status] += 1
        attended += minutes
        if status != "cancelled":
            scheduled += 120
        monday = item.starts_at.astimezone(SAST).date()
        monday -= timedelta(days=monday.weekday())
        week = monday.isoformat()
        weeks.setdefault(week, {"week": monday.strftime("%d %b %Y"), "scheduled_minutes": 0, "attended_minutes": 0})
        weeks[week]["scheduled_minutes"] += 0 if status == "cancelled" else 120
        weeks[week]["attended_minutes"] += minutes
        rows.append(
            {
                "date": date_label(item.starts_at),
                "end": date_label(item.ends_at),
                "tutor": item.tutor.get_full_name().strip() or item.tutor.get_username(),
                "subject": item.subject,
                "level": item.level,
                "topic": item.topic,
                "status": SubscriptionSession.Status(status).label,
                "minutes": minutes,
                "joined": date_label(item.joined_at),
                "left": date_label(item.left_at),
                "learning_summary": item.learning_summary,
                "tutor_feedback": item.tutor_feedback,
                "next_steps": item.next_steps,
            }
        )
    activities = []
    courses = {}
    for item in sub.study_activities.filter(occurred_at__gte=sub.starts_at, occurred_at__lt=sub.ends_at):
        activity = {
            "date": date_label(item.occurred_at),
            "course": item.course_title,
            "lesson": item.lesson_title,
            "percent": item.progress_percent,
            "action": item.get_kind_display(),
        }
        activities.append(activity)
        courses[item.enrollment_id] = activity
    verified_scheduled = 120 * (counts["attended"] + counts["partial"] + counts["absent"])
    return {
        "version": 1,
        "report_id": str(report_id),
        "reference": sub.reference,
        "student": f"{sub.student.first_name} {sub.student.last_name}".strip() or "Amaris student",
        "email": sub.student.email,
        "curriculum": sub.get_curriculum_display(),
        "months": sub.months,
        "amount": str(sub.amount),
        "starts": date_label(sub.starts_at),
        "ends": date_label(sub.ends_at),
        "generated": date_label(timezone.now()),
        "timezone": "South African time (UTC+2)",
        "counts": counts,
        "sessions": rows,
        "weeks": list(weeks.values()),
        "attended_minutes": attended,
        "attended_label": duration_label(attended),
        "scheduled_minutes": scheduled,
        "scheduled_label": duration_label(scheduled),
        "attendance_percent": round(100 * attended / verified_scheduled, 1) if verified_scheduled else None,
        "courses": list(courses.values()),
        "activities": activities,
        "scope_note": "This report uses recorded subscription sessions and course progress milestones. "
        "Scheduled time is not proof of attendance. Course progress is student-reported, not an assessment mark "
        "or video watch time. Unrecorded sessions are excluded from the attendance percentage. "
        "Activities before this tracking feature was enabled are not reconstructed.",
    }


@transaction.atomic
def prepare_report(subscription_id):
    sub = (
        eligible_subscriptions()
        .select_for_update(of=("self",))
        .select_related("student")
        .filter(pk=subscription_id)
        .first()
    )
    if sub is None:
        return None
    report, _ = SubscriptionReport.objects.get_or_create(subscription=sub)
    report = SubscriptionReport.objects.select_for_update().get(pk=report.pk)
    if report.status != "pending":
        return report
    from .subscription_report_document import render_learning_report

    snapshot = report_snapshot(sub, report.pk)
    data = render_learning_report(snapshot)
    if len(data) > MAX_PDF_BYTES:
        raise ValueError("report_attachment_too_large")
    report.pdf_storage_path = storages["student_private"].save(
        f"{sub.student.supabase_user_id}/subscriptions/reports/{report.pk}.pdf", ContentFile(data)
    )
    report.snapshot = snapshot
    report.pdf_sha256 = hashlib.sha256(data).hexdigest()
    report.recipient = sub.student.email
    report.generated_at = timezone.now()
    report.status = SubscriptionReport.Status.READY
    report.error_code = ""
    report.save()
    return report


def _delivery_failed(report_id, *, known_rejected, code):
    report = SubscriptionReport.objects.get(pk=report_id)
    retry = known_rejected and report.attempts < 5
    SubscriptionReport.objects.filter(pk=report_id, status="sending").update(
        status="ready" if retry else "review",
        error_code=code,
        next_attempt_at=timezone.now() + timedelta(minutes=2**report.attempts) if retry else None,
    )


def deliver_report(report_id):
    if not getattr(settings, "SUBSCRIPTION_REPORTS_EMAIL_ENABLED", False):
        return 0
    sub_id = SubscriptionReport.objects.values_list("subscription_id", flat=True).get(pk=report_id)
    with transaction.atomic():
        sub = (
            eligible_subscriptions().select_for_update(of=("self",)).select_related("student").filter(pk=sub_id).first()
        )
        if sub is None:
            return 0
        report = SubscriptionReport.objects.select_for_update().get(pk=report_id)
        if report.status != "ready" or (report.next_attempt_at and report.next_attempt_at > timezone.now()):
            return 0
        if report.recipient != sub.student.email:
            report.status, report.error_code = "review", "recipient_changed"
            report.save(update_fields=["status", "error_code", "updated_at"])
            return 0
        with storages["student_private"].open(report.pdf_storage_path, "rb") as source:
            data = source.read(MAX_PDF_BYTES + 1)
        if len(data) > MAX_PDF_BYTES or hashlib.sha256(data).hexdigest() != report.pdf_sha256:
            report.status, report.error_code = "review", "archive_integrity"
            report.save(update_fields=["status", "error_code", "updated_at"])
            return 0
        snapshot = report.snapshot
        email = EmailMultiAlternatives(
            subject=f"Your Amaris {sub.months}-month learning report - {sub.get_curriculum_display()}",
            body=(
                f"Dear {snapshot['student']},\n\n"
                "Your subscription has ended. Your detailed learning report is attached.\n"
                f"Curriculum: {snapshot['curriculum']}\nPeriod: {snapshot['starts']} to {snapshot['ends']}\n"
                f"Confirmed attendance: {snapshot['attended_label']}\n"
                f"Recorded scheduled time: {snapshot['scheduled_label']}\n"
                f"Unrecorded sessions: {snapshot['counts']['planned']}\n"
                "The PDF includes lesson dates/times, topics, tutor feedback, next steps and course activity.\n"
                f"{snapshot['scope_note']}\n\nThank you for learning with Amaris Mathematics Academy.\n"
                f"Reference: {sub.reference}\nReport: {report.pk}"
            ),
            to=[report.recipient],
            from_email=None,
            headers={
                "Message-ID": make_msgid(
                    idstring=f"subscription-report-{report.pk}",
                    domain=parseaddr(settings.DEFAULT_FROM_EMAIL)[1].rpartition("@")[2] or None,
                ),
                "X-Amaris-Report-ID": str(report.pk),
            },
        )
        email.attach(f"Amaris-learning-report-{sub.reference}.pdf", data, "application/pdf")
        apply_letterhead(email, "Your subscription learning report", email.body.splitlines(), reference=sub.reference)
        # Commit this claim BEFORE SMTP. A crash after acceptance must not auto-resend.
        report.status = "sending"
        report.delivery_started_at = timezone.now()
        report.attempts += 1
        report.save(update_fields=["status", "delivery_started_at", "attempts", "updated_at"])
    try:
        accepted = email.send(fail_silently=False)
    except (SMTPAuthenticationError, SMTPConnectError, SMTPDataError, SMTPRecipientsRefused, SMTPSenderRefused):
        _delivery_failed(report_id, known_rejected=True, code="smtp_rejected")
        return 0
    except Exception:
        _delivery_failed(report_id, known_rejected=False, code="smtp_outcome_unknown")
        return 0
    if accepted != 1:
        _delivery_failed(report_id, known_rejected=True, code="mail_not_accepted")
        return 0
    SubscriptionReport.objects.filter(pk=report_id, status="sending").update(
        status="sent",
        emailed_at=timezone.now(),
        error_code="",
        next_attempt_at=None,
    )
    return 1
