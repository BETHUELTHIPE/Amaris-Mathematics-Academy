"""One encouragement email, 14 days after verified website registration."""

from datetime import timedelta
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.db import connection, transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from content.models import (
    Enrollment,
    LiveClassBooking,
    Payment,
    SiteSettings,
    StudentMotivationEmail,
    StudentRecord,
    VideoRequest,
)
from content.tutor_application_models import TutorApplication

TOKEN_SALT = "content.student-motivation.unsubscribe.v1"


def due_registrations(*, user_id=None, limit=100):
    """Read only the required Auth fields; do not copy tokens or user metadata.

    Use the same database as payments. Missing Auth tables or permissions must
    fail closed rather than substituting the time of a first Django API visit.
    """
    if connection.vendor != "postgresql":
        raise RuntimeError("Student motivation requires the Supabase registration database.")
    receipt_table = connection.ops.quote_name(StudentMotivationEmail._meta.db_table)
    params = [timezone.now() - timedelta(days=14), timezone.now()]
    if user_id is None:
        extra = f"AND NOT EXISTS (SELECT 1 FROM {receipt_table} r WHERE r.supabase_user_id = u.id)"
    else:
        extra = "AND u.id = %s"
        params.append(user_id)
    params.append(limit)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT u.id, u.email, p.first_name, u.created_at
            FROM auth.users u JOIN public.student_profiles p ON p.id = u.id
            WHERE u.created_at <= %s AND u.email_confirmed_at IS NOT NULL
              AND u.deleted_at IS NULL AND (u.banned_until IS NULL OR u.banned_until <= %s)
              AND u.is_anonymous IS NOT TRUE AND u.email IS NOT NULL AND u.email <> ''
              AND COALESCE(u.raw_app_meta_data ->> 'role', 'student') = 'student'
              {extra}
            ORDER BY u.created_at, u.id LIMIT %s
            """,
            params,
        )
        return [dict(zip(("user_id", "email", "first_name", "registered_at"), row, strict=True)) for row in cursor]


def ineligible(user_id, email):
    # Match the account ID and historical email records conservatively. A
    # refund, cancellation after payment or review is still a previous payment.
    students = StudentRecord.objects.filter(Q(supabase_user_id=user_id) | Q(email__iexact=email))
    if students.filter(is_active=False).exists():
        return True
    if get_user_model().objects.filter(email__iexact=email).exists():
        return True
    if TutorApplication.objects.filter(Q(supabase_user_id=user_id) | Q(email__iexact=email)).exists():
        return True
    if (
        Payment.objects.filter(student__in=students)
        .filter(
            Q(status__in=(Payment.Status.PAID, Payment.Status.REFUNDED))
            | Q(paid_at__isnull=False)
            | Q(gateway_verified_at__isnull=False)
        )
        .exists()
    ):
        return True
    if (
        LiveClassBooking.objects.filter(student__in=students)
        .filter(
            Q(status__in=("confirmed", "completed", "payment_review"))
            | Q(paid_at__isnull=False)
            | Q(gateway_verified_at__isnull=False)
        )
        .exists()
    ):
        return True
    if (
        VideoRequest.objects.filter(student__in=students)
        .filter(
            ~Q(status__in=("pending_payment", "cancelled"))
            | Q(paid_at__isnull=False)
            | Q(gateway_verified_at__isnull=False)
        )
        .exists()
    ):
        return True
    return Enrollment.objects.filter(student__in=students, status__in=("active", "completed")).exists()


def queue_due_emails():
    if not settings.STUDENT_MOTIVATION_EMAIL_ENABLED:
        return 0
    queued = 0
    for registration in due_registrations():
        suppressed = ineligible(registration["user_id"], registration["email"])
        _, created = StudentMotivationEmail.objects.get_or_create(
            supabase_user_id=registration["user_id"],
            defaults={
                "registered_at": registration["registered_at"],
                "status": (
                    StudentMotivationEmail.Status.SUPPRESSED if suppressed else StudentMotivationEmail.Status.QUEUED
                ),
            },
        )
        queued += int(created and not suppressed)
    return queued


def unsubscribe_token(user_id):
    return signing.dumps(str(user_id), salt=TOKEN_SALT)


def build_message(registration):
    # The existing payment API URL is environment-specific. Never send a broken
    # opt-out URL or accidentally link staging recipients to production APIs.
    api_url = settings.PUBLIC_API_URL.rstrip("/")
    site_url = settings.PUBLIC_SITE_URL.rstrip("/")
    if any(urlsplit(url).scheme != "https" or not urlsplit(url).netloc for url in (api_url, site_url)):
        raise ValueError("HTTPS public site and API URLs are required for motivation emails.")
    unsubscribe_url = (
        api_url
        + reverse("student-motivation-unsubscribe")
        + "?"
        + urlencode({"token": unsubscribe_token(registration["user_id"])})
    )
    site = SiteSettings.objects.first()
    context = {
        "first_name": registration["first_name"] or "Student",
        "academy": site.site_name if site else "Amaris Mathematics Academy",
        "contact_email": site.email if site else "bethuelmoukangwe8@gmail.com",
        "phone": site.phone if site else "071 415 6665",
        "dashboard_url": site_url + "/dashboard",
        "unsubscribe_url": unsubscribe_url,
    }
    message = EmailMultiAlternatives(
        subject="Your mathematics journey can start with one small step",
        body=render_to_string("emails/student_motivation.txt", context),
        to=[registration["email"]],
        reply_to=[context["contact_email"]],
    )
    message.attach_alternative(render_to_string("emails/student_motivation.html", context), "text/html")
    return message


def deliver_due_email():
    if not settings.STUDENT_MOTIVATION_EMAIL_ENABLED:
        return 0
    # Persist the claim before SMTP. Redelivery after a worker crash must not
    # resend a message whose delivery outcome is unknown.
    with transaction.atomic():
        receipt = (
            StudentMotivationEmail.objects.select_for_update(skip_locked=True)
            .filter(status=StudentMotivationEmail.Status.QUEUED, unsubscribed_at__isnull=True)
            .order_by("registered_at", "pk")
            .first()
        )
        if receipt is None:
            return 0
        registrations = due_registrations(user_id=receipt.supabase_user_id, limit=1)
        if not registrations or ineligible(receipt.supabase_user_id, registrations[0]["email"]):
            receipt.status = StudentMotivationEmail.Status.SUPPRESSED
            receipt.save(update_fields=("status", "updated_at"))
            return 0
        message = build_message(registrations[0])
        receipt.status = StudentMotivationEmail.Status.SENDING
        receipt.attempted_at = timezone.now()
        receipt.save(update_fields=("status", "attempted_at", "updated_at"))
    try:
        # Recheck after claiming, including opt-out/payment arriving in the queue.
        receipt.refresh_from_db()
        if receipt.unsubscribed_at or ineligible(receipt.supabase_user_id, registrations[0]["email"]):
            StudentMotivationEmail.objects.filter(pk=receipt.pk).update(status=StudentMotivationEmail.Status.SUPPRESSED)
            return 0
        if message.send(fail_silently=False) != 1:
            raise OSError("Motivation email was not accepted.")
    except Exception as exc:
        StudentMotivationEmail.objects.filter(pk=receipt.pk).update(
            status=StudentMotivationEmail.Status.REVIEW, last_error_code=type(exc).__name__[:120]
        )
        # No raw SMTP exception text or recipient data in task logs.
        return 0
    StudentMotivationEmail.objects.filter(pk=receipt.pk).update(
        status=StudentMotivationEmail.Status.SENT, sent_at=timezone.now(), last_error_code=""
    )
    return 1
