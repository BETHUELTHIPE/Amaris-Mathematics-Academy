"""Bounded, database-aggregated rankings of verified activity, with explicit provenance."""

from datetime import datetime, time, timedelta
from decimal import Decimal
from functools import reduce
from operator import or_
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Min, Q, Sum, Value
from django.db.models.functions import Lower, Replace, Trim
from django.utils import timezone

from content.models import LiveClassBooking, Payment, TutorAvailabilitySlot, VideoRequest

SAST = ZoneInfo("Africa/Johannesburg")
TOP = 20
VIDEO_STATES = ("queued", "tutor_assigned", "recording", "processing", "review", "ready")
METHODOLOGY = (
    "Rankings count verified positive-value ZAR orders in the selected environment, by gateway verification date.",
    "Pending, failed, cancelled, refunded, payment-review and legacy unclassified orders do not enter the rankings.",
    "Tutor ranking measures new paid Zoom bookings, not teaching quality. "
    "Unique booking learners, booked hours and recorded completion provide context.",
    "Recorded completed status is not measured attendance. "
    "Future lessons are excluded from the due-lesson completion denominator.",
    "Topic spelling is grouped by case and whitespace within curriculum, subject, level and request type. "
    "Synonyms remain separate.",
    "Values are base-order gross amounts before fees, not profit or tutor payouts. "
    "Video priority add-ons and subscription sales are not included.",
    "Snapshots freeze status and assigned tutor at generation time. "
    "Late refunds or staff edits do not rewrite archived reports.",
    "Popularity depends on availability and exposure. "
    "Use these indicators with lesson feedback and delivery review before making staff decisions.",
)


def bounds(start, end):
    return datetime.combine(start, time.min, SAST), datetime.combine(end, time.min, SAST)


def money(value):
    return str(Decimal(value or 0).quantize(Decimal("0.01")))


def hours(value):
    return money(Decimal(str(value.total_seconds())) / Decimal(3600)) if value else "0.00"


def normalised(field):
    value = Replace(F(field), Value("\t"), Value(" "))
    for character in ("\n", "\r"):
        value = Replace(value, Value(character), Value(" "))
    for _ in range(8):  # Collapse any run within the model's <=180-character topic field.
        value = Replace(value, Value("  "), Value(" "))
    return Lower(Trim(value))


def change(current, previous):
    if not previous:
        return "New activity" if current else "No activity"
    amount = (Decimal(current - previous) * 100 / previous).quantize(Decimal("0.1"))
    return f"{amount:+}% vs previous 14 days"


def ranked(rows, previous, keys):
    conditions = [Q(**{key: row[key] for key in keys}) for row in rows]
    earlier = {}
    if conditions:
        earlier = {tuple(row[key] for key in keys): row["count"] for row in previous.filter(reduce(or_, conditions))}
    last, rank = None, 0
    maximum = max((row["count"] for row in rows), default=1)
    for row in rows:
        if row["count"] != last:
            rank += 1
        last = row["count"]
        row["rank"] = rank
        row["previous_count"] = earlier.get(tuple(row[key] for key in keys), 0)
        row["change"] = change(row["count"], row["previous_count"])
        row["bar"] = round(row["count"] * 100 / maximum)
    return rows


def sources(start, end, mode):
    lower, upper = bounds(start, end)
    common = dict(
        payment_mode=mode,
        gateway_verified_at__gte=lower,
        gateway_verified_at__lt=upper,
        paid_at__isnull=False,
        currency="ZAR",
        amount__gt=0,
    )
    return (
        LiveClassBooking.objects.filter(status__in=("confirmed", "completed"), **common),
        VideoRequest.objects.filter(status__in=VIDEO_STATES, **common),
        Payment.objects.filter(status="paid", **common),
    )


def totals(queries):
    values = []
    gross = Decimal(0)
    for query in queries:
        summary = query.aggregate(count=Count("pk"), gross=Sum("amount"))
        values.append(summary["count"])
        gross += summary["gross"] or Decimal(0)
    return {"bookings": values[0], "video_requests": values[1], "course_purchases": values[2], "gross": money(gross)}


def tutor_groups(query, upper):
    duration = ExpressionWrapper(F("slot__ends_at") - F("slot__starts_at"), output_field=DurationField())
    return (
        query.order_by()
        .values("slot__tutor_id", "slot__tutor__first_name", "slot__tutor__last_name", "slot__tutor__username")
        .annotate(
            count=Count("pk"),
            learners=Count("student_id", distinct=True),
            gross=Sum("amount"),
            booked_time=Sum(duration),
            due=Count("pk", filter=Q(slot__ends_at__lt=upper)),
            completed_due=Count("pk", filter=Q(status="completed", slot__ends_at__lt=upper)),
        )
    )


def topic_groups(query):
    duration = ExpressionWrapper(F("video_ready_at") - F("gateway_verified_at"), output_field=DurationField())
    return (
        query.annotate(topic_key=normalised("topic"), level_key=normalised("level"))
        .order_by()
        .values("topic_key", "level_key", "programme", "subject", "request_type")
        .annotate(
            count=Count("pk"),
            learners=Count("student_id", distinct=True),
            label=Min("topic"),
            level_label=Min("level"),
            gross=Sum("amount"),
            ready=Count("pk", filter=Q(status="ready")),
            average_turnaround=Avg(duration, filter=Q(status="ready", video_ready_at__gte=F("gateway_verified_at"))),
        )
    )


def course_groups(query):
    return (
        query.order_by()
        .values("course_id", "course__title", "course__curriculum", "course__academic_level")
        .annotate(count=Count("pk"), learners=Count("student_id", distinct=True), gross=Sum("amount"))
    )


def build_snapshot(start, end, mode):
    if mode not in {"live", "sandbox"} or end - start != timedelta(days=14):
        raise ValueError("Use a 14-day period and a known payment environment.")
    lower, upper = bounds(start, end)
    if upper > timezone.now():
        raise ValueError("The reporting period must have ended.")
    current = sources(start, end, mode)
    previous = sources(start - timedelta(days=14), start, mode)
    current_totals, previous_totals = totals(current), totals(previous)
    tutors = ranked(
        list(tutor_groups(current[0], upper).order_by("-count", "slot__tutor_id")[:TOP]),
        tutor_groups(previous[0], lower),
        ["slot__tutor_id"],
    )
    for row in tutors:
        row["name"] = f"{row.pop('slot__tutor__first_name')} {row.pop('slot__tutor__last_name')}".strip() or row.pop(
            "slot__tutor__username"
        )
        row.pop("slot__tutor__username", None)
        row["tutor_id"] = row.pop("slot__tutor_id")
        row["booked_hours"] = hours(row.pop("booked_time"))
        row["gross"] = money(row["gross"])
        row["completion"] = f"{row['completed_due'] * 100 / row['due']:.0f}%" if row["due"] else "Not due"
    keys = ["topic_key", "level_key", "programme", "subject", "request_type"]
    topics = ranked(list(topic_groups(current[1]).order_by("-count", *keys)[:TOP]), topic_groups(previous[1]), keys)
    for row in topics:
        row["name"], row["level"] = " ".join(row.pop("label").split()), " ".join(row.pop("level_label").split())
        row["curriculum"] = dict(TutorAvailabilitySlot.Programme.choices).get(row["programme"], row["programme"])
        row["subject_label"] = dict(TutorAvailabilitySlot.Subject.choices).get(row["subject"], row["subject"])
        row["request_label"] = dict(VideoRequest.RequestType.choices).get(row["request_type"], row["request_type"])
        row["backlog"] = row["count"] - row["ready"]
        row["gross"] = money(row["gross"])
        duration = row.pop("average_turnaround")
        row["turnaround"] = f"{duration.total_seconds() / 86400:.1f} days" if duration is not None else "Not recorded"
    courses = ranked(
        list(course_groups(current[2]).order_by("-count", "course_id")[:TOP]), course_groups(previous[2]), ["course_id"]
    )
    for row in courses:
        row["name"], row["curriculum"], row["level"] = (
            row.pop("course__title"),
            row.pop("course__curriculum"),
            row.pop("course__academic_level"),
        )
        row["gross"] = money(row["gross"])
    delivered = (
        VideoRequest.objects.filter(
            payment_mode=mode,
            currency="ZAR",
            amount__gt=0,
            paid_at__isnull=False,
            gateway_verified_at__isnull=False,
            status="ready",
            video_ready_at__gte=lower,
            video_ready_at__lt=upper,
            assigned_tutor__isnull=False,
        )
        .exclude(video_external_id="")
        .order_by()
        .values(
            "assigned_tutor_id", "assigned_tutor__first_name", "assigned_tutor__last_name", "assigned_tutor__username"
        )
        .annotate(count=Count("pk"))
        .order_by("-count", "assigned_tutor_id")[:10]
    )
    delivery_leaders = [
        {
            "tutor_id": row["assigned_tutor_id"],
            "name": f"{row['assigned_tutor__first_name']} {row['assigned_tutor__last_name']}".strip()
            or row["assigned_tutor__username"],
            "count": row["count"],
        }
        for row in delivered
    ]
    no_bookings = (
        get_user_model()
        .objects.filter(is_active=True, groups__name="Tutors")
        .exclude(pk__in=current[0].values("slot__tutor_id"))
        .distinct()
    )
    unclassified, review = 0, 0
    for model in (LiveClassBooking, VideoRequest, Payment):
        paid = model.objects.filter(
            gateway_verified_at__gte=lower,
            gateway_verified_at__lt=upper,
            paid_at__isnull=False,
            currency="ZAR",
            amount__gt=0,
        )
        unclassified += paid.filter(payment_mode="unknown").count()
        if model is not Payment:
            review += paid.filter(payment_mode=mode, status="payment_review").count()
    result = {
        "version": 1,
        "mode": mode,
        "start": str(start),
        "end": str(end),
        "last_day": str(end - timedelta(days=1)),
        "generated_at": timezone.now().astimezone(SAST).strftime("%d %B %Y %H:%M SAST"),
        "totals": current_totals,
        "previous": previous_totals,
        "changes": {
            key: change(current_totals[key], previous_totals[key])
            for key in ("bookings", "video_requests", "course_purchases")
        },
        "tutors": tutors,
        "topics": topics,
        "courses": courses,
        "delivery_leaders": delivery_leaders,
        "unbooked_tutors": no_bookings.count(),
        "unclassified_orders": unclassified,
        "payment_review_orders": review,
        "methodology": list(METHODOLOGY),
        "weekly": [
            dict(start=str(day), **totals(sources(day, day + timedelta(days=7), mode)))
            for day in (start, start + timedelta(days=7))
        ],
    }
    return result


def report_sections(snapshot):
    s = snapshot
    sections = [
        (
            "Report overview",
            [
                f"Period: {s['start']} to {s['last_day']} inclusive (SAST)",
                f"Environment: {s['mode'].upper()}",
                f"Generated: {s['generated_at']}",
                f"Paid Zoom bookings: {s['totals']['bookings']} ({s['changes']['bookings']})",
                f"Paid video requests: {s['totals']['video_requests']} ({s['changes']['video_requests']})",
                f"Course purchases: {s['totals']['course_purchases']} ({s['changes']['course_purchases']})",
                f"Verified base-order gross: R{s['totals']['gross']}",
            ],
        )
    ]
    sections += [
        (
            "Most booked tutors",
            [
                f"#{r['rank']} {r['name']} - {r['count']} bookings; {r['learners']} learners; "
                f"{r['booked_hours']} booked hours; R{r['gross']}; "
                f"{r['completed_due']}/{r['due']} due lessons recorded complete; {r['change']}"
                for r in s["tutors"]
            ],
        ),
        (
            "Most requested paid video topics",
            [
                f"#{r['rank']} {r['name']} - {r['curriculum']} / {r['subject_label']} / "
                f"{r['level']} / {r['request_label']}: {r['count']} requests; "
                f"{r['backlog']} currently outstanding; "
                f"{r['turnaround']} average recorded turnaround; {r['change']}"
                for r in s["topics"]
            ],
        ),
        (
            "Most purchased courses",
            [
                f"#{r['rank']} {r['name']} - {r['curriculum']} / {r['level']}: "
                f"{r['count']} purchases; {r['learners']} buyers; R{r['gross']}; {r['change']}"
                for r in s["courses"]
            ],
        ),
        (
            "Video delivery leaders",
            [f"{r['name']}: {r['count']} videos marked ready during the period" for r in s["delivery_leaders"]],
        ),
        (
            "Follow-up and data quality",
            [
                f"Active approved tutors with no new verified Zoom bookings: {s['unbooked_tutors']}. "
                "Check availability and exposure before drawing conclusions.",
                f"Legacy/unclassified positive verified orders excluded: {s['unclassified_orders']}.",
                f"Paid orders awaiting payment review excluded: {s['payment_review_orders']}.",
                f"Earlier completed periods without an archive: {s.get('missing_periods', 0)}. "
                "After downtime, only the most recent completed period is generated to avoid an email flood.",
                "Review high-demand topics with an outstanding queue when planning the next recording slots.",
            ],
        ),
        ("How to read this report", s["methodology"]),
    ]
    return [(heading, lines or ["No qualifying activity in this period."]) for heading, lines in sections]
