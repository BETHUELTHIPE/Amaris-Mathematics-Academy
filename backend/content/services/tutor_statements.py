"""Private, professional 30-day tutor activity and earnings snapshots.

No payout is initiated. Snapshots use verified ledger entries, not expected fees,
and deliberately exclude student names, emails, Zoom links and bank accounts.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from content.models import LiveClassBooking, SiteSettings, VideoRequest
from content.tutor_finance_models import TutorActivityStatement, TutorEarning, TutorPayout

PERIOD_DAYS = 30
ZERO = Decimal("0.00")


def _money(value):
    return str(Decimal(value or 0).quantize(Decimal("0.01")))


def _sast(value):
    return timezone.localtime(value).strftime("%d %b %Y %H:%M SAST")


def activity_snapshot(tutor, start, end):
    """Bound by [start, end); count only delivered paid classes and attributed videos."""
    completed = list(
        LiveClassBooking.objects.filter(
            slot__tutor=tutor,
            status=LiveClassBooking.Status.COMPLETED,
            gateway_verified_at__isnull=False,
            slot__ends_at__gte=start,
            slot__ends_at__lt=end,
        )
        .select_related("slot")
        .order_by("slot__ends_at", "reference")
    )
    videos = list(
        VideoRequest.objects.filter(
            assigned_tutor=tutor,
            gateway_verified_at__isnull=False,
            paid_at__gte=start,
            paid_at__lt=end,
        ).order_by("paid_at", "reference")
    )
    earnings = list(
        TutorEarning.objects.filter(
            tutor=tutor,
            payment_verified_at__gte=start,
            payment_verified_at__lt=end,
        ).order_by("payment_verified_at", "source_reference")
    )
    paid = list(
        TutorPayout.objects.filter(
            earning__tutor=tutor,
            state=TutorPayout.State.PAID,
            confirmed_at__gte=start,
            confirmed_at__lt=end,
        )
        .exclude(provider_reference="")
        .select_related("earning")
        .order_by("confirmed_at")
    )
    students_taught = {x.student_id for x in completed}
    students = students_taught | {x.student_id for x in videos}
    valid = [x for x in earnings if x.state != TutorEarning.State.REVERSED]
    by_state = {
        state: _money(sum((x.tutor_amount for x in valid if x.state == state), ZERO))
        for state in (TutorEarning.State.HELD, TutorEarning.State.READY, TutorEarning.State.PAID)
    }
    return {
        "currency": "ZAR",
        "tutor_name": tutor.get_full_name().strip() or tutor.get_username(),
        "tutor_email": tutor.email,
        "period_start": _sast(start),
        "period_end_exclusive": _sast(end),
        "unique_students": len(students),
        "students_taught": len(students_taught),
        "sessions_taught": len(completed),
        "hours_taught": sum((x.slot.duration_hours for x in completed), 0),
        "video_requests": len(videos),
        "videos_delivered": sum(1 for x in videos if x.status == VideoRequest.Status.READY and x.video_ready_at),
        "paid_video_requests": len(videos),
        "earnings_count": len(valid),
        "gross_verified": _money(sum((x.gross for x in valid), ZERO)),
        "tutor_share": _money(sum((x.tutor_amount for x in valid), ZERO)),
        "academy_share": _money(sum((x.academy_amount for x in valid), ZERO)),
        "held_earnings": by_state[TutorEarning.State.HELD],
        "ready_earnings": by_state[TutorEarning.State.READY],
        "ledger_paid_state": by_state[TutorEarning.State.PAID],
        "reversed_count": len(earnings) - len(valid),
        "confirmed_payouts_in_period": _money(sum((x.earning.tutor_amount for x in paid), ZERO)),
        "confirmed_payout_count": len(paid),
        "session_activity": [
            {
                "date": _sast(x.slot.ends_at),
                "reference": x.reference,
                "activity": f"Completed class / {x.topic[:100]}",
                "hours": x.slot.duration_hours,
            }
            for x in completed
        ],
        "video_activity": [
            {
                "date": _sast(x.paid_at),
                "reference": x.reference,
                "activity": f"Paid video request / {x.topic[:100]}",
                "status": x.status,
            }
            for x in videos
        ],
        "ledger_lines": [
            {
                "date": _sast(x.payment_verified_at),
                "reference": x.source_reference,
                "service": x.get_service_display(),
                "gross": _money(x.gross),
                "tutor_share": _money(x.tutor_amount),
                "status": x.state,
            }
            for x in earnings
        ],
        "payout_lines": [
            {
                "date": _sast(x.confirmed_at),
                "reference": x.provider_reference[:80],
                "amount": _money(x.earning.tutor_amount),
            }
            for x in paid
        ],
        "disclaimer": (
            "Tutor earnings reflect server-verified sales and signed contract splits. "
            "Held and eligible amounts are NOT evidence of a bank transfer. "
            "Only payouts with confirmed provider references are shown as paid. "
            "Refunds/reversals are excluded from current earnings and identified separately."
        ),
    }


def issue_due_statements(now=None, limit=100):
    """Daily beat: first issue last 30 complete SAST days, then contiguous 30-day windows.

    Lock the tutor row to prevent simultaneous workers issuing different periods.
    Database unique keys protect against retries. No mass backfill from registration date.
    """
    now = timezone.localtime(now or timezone.now())
    period_anchor = now.replace(hour=0, minute=0, second=0, microsecond=0)
    due = 0
    tutor_ids = list(
        get_user_model()
        .objects.filter(is_active=True)
        .filter(Q(finance_contracts__is_active=True) | Q(groups__name__iexact="Tutors"))
        .distinct()
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    for tutor_id in tutor_ids:
        if due >= limit:
            break
        with transaction.atomic():
            tutor = get_user_model().objects.select_for_update().get(pk=tutor_id)
            previous = TutorActivityStatement.objects.filter(tutor=tutor).order_by("-period_end").first()
            if previous:
                start = previous.period_end
                end = start + timedelta(days=PERIOD_DAYS)
                if end > period_anchor:
                    continue
            else:
                end = period_anchor
                start = end - timedelta(days=PERIOD_DAYS)
            number = f"ATS-{start:%Y%m%d}-{end:%Y%m%d}-T{tutor.pk:07d}"
            _, created = TutorActivityStatement.objects.get_or_create(
                tutor=tutor,
                period_start=start,
                period_end=end,
                defaults={
                    "report_number": number,
                    "snapshot": activity_snapshot(tutor, start, end),
                },
            )
            due += int(created)
    return due


def _pdf_value(value):
    from content.services.invoice_document import _paragraph

    return _paragraph(str(value), size=7.4)


def render_tutor_statement_pdf(statement):
    """A4 PDF on the established Amaris logo, colour, contact and font system."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import LongTable, SimpleDocTemplate, Spacer, Table, TableStyle

    from content.services.invoice_document import (
        BLUE,
        GOLD,
        LINE,
        NAVY,
        SLATE,
        _logo,
        _paragraph,
        _register_fonts,
    )

    _register_fonts()
    details = statement.snapshot
    site = SiteSettings.objects.first() or SiteSettings()
    logo = _logo(site)
    width, height = A4
    out = BytesIO()

    def heading(page, doc):
        page.saveState()
        page.setTitle(f"Amaris tutor statement {statement.report_number}")
        page.setAuthor("Amaris Mathematics Academy")
        page.setFillColor(NAVY)
        page.rect(0, height - 6, width * 0.62, 6, fill=1, stroke=0)
        page.setFillColor(BLUE)
        page.rect(width * 0.62, height - 6, width * 0.28, 6, fill=1, stroke=0)
        page.setFillColor(GOLD)
        page.rect(width * 0.9, height - 6, width * 0.1, 6, fill=1, stroke=0)
        page.drawImage(logo, 38, height - 91, 53, 53, preserveAspectRatio=True, mask="auto")
        page.setFillColor(NAVY)
        page.setFont("AmarisSans-Bold", 14)
        page.drawString(105, height - 56, "Amaris Mathematics Academy")
        page.setFont("AmarisSans", 8)
        page.drawString(105, height - 76, "TUTOR ACTIVITY & EARNINGS STATEMENT")
        page.setStrokeColor(LINE)
        page.line(38, height - 112, width - 38, height - 112)
        page.line(38, 61, width - 38, 61)
        page.setFont("AmarisSans", 6.5)
        page.setFillColor(SLATE)
        page.drawString(38, 48, f"{site.email}  |  {site.phone}")
        page.drawRightString(width - 38, 48, f"Page {doc.page}  |  Private statement")
        page.restoreState()

    doc = SimpleDocTemplate(
        out,
        pagesize=A4,
        leftMargin=38,
        rightMargin=38,
        topMargin=132,
        bottomMargin=76,
        title=statement.report_number,
    )
    flow = [
        _paragraph("PRIVATE • 30-DAY REPORT", color=BLUE, bold=True, size=9),
        Spacer(1, 8),
        _paragraph(details["tutor_name"], color=NAVY, bold=True, size=15),
        _paragraph(details["tutor_email"], size=8),
        _paragraph(
            f"Reporting period: {details['period_start']} to {details['period_end_exclusive']} (exclusive)", size=8
        ),
        _paragraph(f"Statement reference: {statement.report_number}", size=8),
        Spacer(1, 16),
    ]

    summary = [
        ("Students taught / served", details["unique_students"]),
        ("Completed classes", details["sessions_taught"]),
        ("Teaching hours", details["hours_taught"]),
        ("Paid video requests assigned", details["video_requests"]),
        ("Ready videos", details["videos_delivered"]),
        ("Verified gross sales", "R " + details["gross_verified"]),
        ("Tutor share accrued", "R " + details["tutor_share"]),
        ("Academy share", "R " + details["academy_share"]),
        ("Held tutor earnings", "R " + details["held_earnings"]),
        ("Eligible tutor earnings", "R " + details["ready_earnings"]),
        ("Provider-confirmed payouts during period", "R " + details["confirmed_payouts_in_period"]),
        ("Reversed ledger entries", details["reversed_count"]),
    ]
    rows = [[_pdf_value(k), _pdf_value(v)] for k, v in summary]
    table = Table(rows, colWidths=[335, 184], repeatRows=0)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f5f7fb")),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f5f7fb")]),
                ("LINEBELOW", (0, 0), (-1, -1), 0.45, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    flow += [table, Spacer(1, 13), _paragraph(details["disclaimer"], size=7.5), Spacer(1, 18)]

    def section(title, labels, items, keys):
        flow.append(_paragraph(title, color=BLUE, bold=True, size=10))
        flow.append(Spacer(1, 7))
        data = [[_paragraph(x, size=7, color=colors.white, bold=True) for x in labels]]
        if items:
            for item in items:
                data.append([_pdf_value(item.get(k, "")) for k in keys])
        else:
            data.append([_pdf_value("No verified activity in this period")] + [_pdf_value("")] * (len(keys) - 1))
        widths = [113, 110, 296] if len(keys) == 3 else [85, 99, 95, 74, 82, 84] if len(keys) == 6 else [125, 250, 144]
        if len(widths) != len(keys):
            widths = [519 / len(keys)] * len(keys)
        tab = LongTable(data, colWidths=widths, repeatRows=1)
        tab.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.35, LINE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        flow.extend([tab, Spacer(1, 16)])

    section(
        "Completed teaching sessions",
        ("Date", "Reference", "Activity"),
        details["session_activity"],
        ("date", "reference", "activity"),
    )
    section(
        "Tutor video requests",
        ("Date", "Reference", "Activity / status"),
        [{**row, "activity": row["activity"] + " — " + row["status"]} for row in details["video_activity"]],
        ("date", "reference", "activity"),
    )
    section(
        "Verified earnings ledger",
        ("Date", "Reference", "Service", "Gross", "Tutor share", "Status"),
        details["ledger_lines"],
        ("date", "reference", "service", "gross", "tutor_share", "status"),
    )
    section(
        "Provider-confirmed bank payouts",
        ("Date", "Reference", "Paid amount"),
        [{**row, "amount": "R " + row["amount"]} for row in details["payout_lines"]],
        ("date", "reference", "amount"),
    )
    doc.build(flow, onFirstPage=heading, onLaterPages=heading)
    pdf = out.getvalue()
    if not pdf.startswith(b"%PDF") or len(pdf) > 15_000_000:
        raise ValueError("Invalid or unexpectedly large statement PDF")
    return pdf


def archive_statement(statement):
    """Save into the private administrator Supabase S3 bucket, never a public URL."""
    if settings.SUPABASE_S3_ADMIN_BUCKET != "amaris-cms-files" or not settings.SUPABASE_S3_ENDPOINT_URL:
        raise RuntimeError("Private Supabase admin bucket is not configured")
    key = f"tutor-statements/{statement.period_end:%Y}/{statement.tutor_id}/{statement.report_number}.pdf"
    storage = storages["default"]
    pdf = render_tutor_statement_pdf(statement)
    digest = hashlib.sha256(pdf).hexdigest()
    if storage.exists(key):
        with storage.open(key, "rb") as f:
            if hashlib.sha256(f.read()).hexdigest() != digest:
                raise RuntimeError("Statement archive conflicts with previously issued PDF")
    else:
        saved_key = storage.save(key, ContentFile(pdf))
        if saved_key != key:
            raise RuntimeError("Private statement storage changed immutable archive key")
    statement.pdf_storage_path = key
    statement.pdf_sha256 = digest
    statement.state = TutorActivityStatement.State.ARCHIVED
    statement.save(update_fields=["pdf_storage_path", "pdf_sha256", "state", "updated_at"])
    return pdf
