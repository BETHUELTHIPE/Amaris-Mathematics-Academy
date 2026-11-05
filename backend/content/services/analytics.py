"""Private, read-only analytics. Aggregate in SQL; never serialize people or payment references."""

from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from content.models import Enrollment, LiveClassBooking, Payment, VideoRequest
from content.tutor_finance_models import TutorEarning, TutorPayout

SAST = ZoneInfo("Africa/Johannesburg")
PAID_VIDEO_STATES = (
    "queued",
    "tutor_assigned",
    "recording",
    "processing",
    "review",
    "ready",
)


def _window(days):
    now = timezone.now()
    today = now.astimezone(SAST).date()
    first = today - timedelta(days=days - 1)
    start = datetime.combine(first, time.min, tzinfo=SAST)
    dates = [(first + timedelta(days=index)).isoformat() for index in range(days)]
    return start, now, dates


def _series(qs, field, start, end, *, amount=None, duration=False):
    rows = qs.filter(**{f"{field}__gte": start, f"{field}__lte": end})
    expression = Sum(amount) if amount is not None else Count("pk")
    result = rows.annotate(day=TruncDate(field, tzinfo=SAST)).values("day").annotate(value=expression).order_by("day")
    values = {}
    for row in result:
        value = row["value"]
        if duration:
            value = round(value.total_seconds() / 3600, 2) if value else 0
        elif amount is not None:
            value = int((value or Decimal("0")) * 100)
        values[row["day"].isoformat()] = value or 0
    return values


def _metric(key, title, unit, description, dates, sources):
    # Each source is a bounded daily aggregate, not raw order rows.
    series = [{"date": date, "value": sum(values.get(date, 0) for _, values in sources)} for date in dates]
    return {
        "key": key,
        "title": title,
        "unit": unit,
        "description": description,
        "total": round(sum(item["value"] for item in series), 2),
        "series": series,
        "breakdown": [{"label": label, "value": round(sum(values.values()), 2)} for label, values in sources],
    }


def _class_hours(bookings, start, end):
    hours = bookings.filter(slot__ends_at__gt=F("slot__starts_at"))
    duration = ExpressionWrapper(F("slot__ends_at") - F("slot__starts_at"), output_field=DurationField())
    return _series(hours, "slot__starts_at", start, end, amount=duration, duration=True)


def _result(role, days, start, end, metrics, progress):
    return {
        "version": 1,
        "role": role,
        "period": {
            "days": days,
            "start": start.date().isoformat(),
            "end": end.astimezone(SAST).date().isoformat(),
            "timezone": "Africa/Johannesburg",
        },
        "generated_at": end.isoformat(),
        "metrics": metrics,
        "progress": progress,
    }


def student_analytics(student, days):
    start, end, dates = _window(days)
    courses = Payment.objects.filter(
        student=student,
        status=Payment.Status.PAID,
        currency="ZAR",
        gateway_verified_at__isnull=False,
        paid_at__isnull=False,
    )
    classes = LiveClassBooking.objects.filter(
        student=student,
        status__in=("confirmed", "completed"),
        currency="ZAR",
        gateway_verified_at__isnull=False,
        paid_at__isnull=False,
    )
    videos = VideoRequest.objects.filter(
        student=student,
        status__in=PAID_VIDEO_STATES,
        currency="ZAR",
        gateway_verified_at__isnull=False,
        paid_at__isnull=False,
    )
    paid_sources = [
        ("Courses", courses),
        ("Live classes", classes),
        ("Requested videos", videos),
    ]
    metrics = [
        _metric(
            "paid_services",
            "Paid learning services",
            "count",
            "Verified paid services, grouped by payment date. Refunded, cancelled and review orders are excluded.",
            dates,
            [(label, _series(qs, "paid_at", start, end)) for label, qs in paid_sources],
        ),
        _metric(
            "spending",
            "Verified spending",
            "cents",
            "Current verified ZAR purchases, grouped by payment date; this is not a bank statement.",
            dates,
            [(label, _series(qs, "paid_at", start, end, amount="amount")) for label, qs in paid_sources],
        ),
        _metric(
            "lesson_hours",
            "Scheduled lesson hours",
            "hours",
            "Paid confirmed/completed classes starting within this period, up to now. Hours do not prove attendance.",
            dates,
            [("Live classes", _class_hours(classes, start, end))],
        ),
        _metric(
            "video_requests",
            "Video requests submitted",
            "count",
            "Requests created during this period, including requests still awaiting payment.",
            dates,
            [
                (
                    "Video requests",
                    _series(
                        VideoRequest.objects.filter(student=student),
                        "created_at",
                        start,
                        end,
                    ),
                )
            ],
        ),
    ]
    enrollments = Enrollment.objects.filter(student=student, status__in=("active", "completed"))
    aggregate = enrollments.aggregate(
        total=Count("pk"),
        average=Avg("progress_percent"),
        completed=Count("pk", filter=Q(status="completed")),
    )
    progress = {
        "title": "Your learning progress",
        "percent": round(float(aggregate["average"] or 0), 1),
        "completed": aggregate["completed"],
        "total": aggregate["total"],
        "description": (
            "Average saved progress across current course enrolments, independent of the date filter. "
            "This is not an exam result or certificate."
        ),
    }
    return _result("student", days, start, end, metrics, progress)


def tutor_analytics(tutor, days):
    start, end, dates = _window(days)
    earnings = TutorEarning.objects.filter(tutor=tutor, currency="ZAR", payment_verified_at__isnull=False).exclude(
        state=TutorEarning.State.REVERSED
    )
    payouts = (
        TutorPayout.objects.filter(
            earning__tutor=tutor,
            earning__currency="ZAR",
            state=TutorPayout.State.PAID,
            confirmed_at__isnull=False,
        )
        .exclude(provider_reference="")
        .exclude(earning__state=TutorEarning.State.REVERSED)
    )
    services = [
        ("Courses", "course"),
        ("Live classes", "live_class"),
        ("Requested videos", "video"),
    ]
    classes = LiveClassBooking.objects.filter(
        slot__tutor=tutor,
        status__in=("confirmed", "completed"),
        currency="ZAR",
        gateway_verified_at__isnull=False,
        paid_at__isnull=False,
    )
    ready = VideoRequest.objects.filter(
        assigned_tutor=tutor,
        status="ready",
        gateway_verified_at__isnull=False,
        paid_at__isnull=False,
        video_ready_at__isnull=False,
    )
    metrics = [
        _metric(
            "earnings",
            "Recorded tutor earnings",
            "cents",
            "Your verified earnings ledger, including held amounts. "
            "Reversed entries are excluded; earnings are not bank payouts.",
            dates,
            [
                (
                    label,
                    _series(
                        earnings.filter(service=service),
                        "payment_verified_at",
                        start,
                        end,
                        amount="tutor_amount",
                    ),
                )
                for label, service in services
            ],
        ),
        _metric(
            "payouts",
            "Confirmed payouts",
            "cents",
            "Provider-confirmed payouts by confirmation date. "
            "Processing, failed and unconfirmed transfers are excluded.",
            dates,
            [
                (
                    label,
                    _series(
                        payouts.filter(earning__service=service),
                        "confirmed_at",
                        start,
                        end,
                        amount="earning__tutor_amount",
                    ),
                )
                for label, service in services
            ],
        ),
        _metric(
            "lesson_hours",
            "Scheduled teaching hours",
            "hours",
            "Paid confirmed/completed classes starting in the selected period, up to now. Attendance is not inferred.",
            dates,
            [("Live classes", _class_hours(classes, start, end))],
        ),
        _metric(
            "videos_ready",
            "Video lessons ready",
            "count",
            "Assigned, paid requests marked ready in the selected period.",
            dates,
            [("Video lessons", _series(ready, "video_ready_at", start, end))],
        ),
    ]
    past = classes.filter(slot__starts_at__gte=start, slot__ends_at__lte=end)
    total = past.count()
    completed = past.filter(status="completed").count()
    progress = {
        "title": "Recorded class completion",
        "percent": round(completed / total * 100, 1) if total else 0,
        "completed": completed,
        "total": total,
        "description": (
            "Classes recorded as completed out of past paid classes in this period. "
            "Future sessions are excluded; attendance is not inferred."
        ),
    }
    return _result("tutor", days, start, end, metrics, progress)
