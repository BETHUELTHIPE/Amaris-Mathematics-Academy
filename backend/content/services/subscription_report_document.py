"""A4 learning report using the academy's existing logo, fonts and letterhead colours."""

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import LongTable, PageBreak, SimpleDocTemplate, Spacer, Table, TableStyle

from content.services.invoice_document import ASSETS, BLUE, GOLD, LINE, NAVY, SLATE, _paragraph, _register_fonts


def render_learning_report(report):
    _register_fonts()
    output = BytesIO()
    width, height = A4
    margin = 40
    usable = width - margin * 2
    story = []

    def p(text, size=9, bold=False, color=SLATE):
        return _paragraph(text, size=size, bold=bold, color=color)

    def heading(text):
        item = p(text, 14, True, NAVY)
        item.style.keepWithNext = True
        story.extend([Spacer(1, 14), item, Spacer(1, 6)])

    def table(headers, rows, widths):
        data = [[p(h, 8, True, colors.white) for h in headers]]
        data += [[p(c, 8) for c in row] for row in rows]
        item = LongTable(data, colWidths=widths, repeatRows=1, splitInRow=1)
        item.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f6fc")]),
                    ("LINEBELOW", (0, 0), (-1, 0), 2, GOLD),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                    ("TOPPADDING", (0, 0), (-1, -1), 9),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(item)

    def page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, height - 13, width, 13, fill=1, stroke=0)
        canvas.drawImage(str(ASSETS / "amaris-academy-icon-192.png"), margin, height - 80, 46, 46, mask="auto")
        canvas.setFont("AmarisSans-Bold", 14)
        canvas.drawString(margin + 58, height - 51, "AMARIS MATHEMATICS ACADEMY")
        canvas.setFillColor(SLATE)
        canvas.setFont("AmarisSans", 8)
        canvas.drawString(margin + 58, height - 68, "Personal learning report | Subscription completion")
        canvas.setStrokeColor(GOLD)
        canvas.line(margin, height - 94, width - margin, height - 94)
        canvas.setStrokeColor(LINE)
        canvas.line(margin, 43, width - margin, 43)
        canvas.setFont("AmarisSans", 7)
        canvas.drawString(margin, 29, f"Private student record | {report['reference']}")
        canvas.drawRightString(width - margin, 29, f"SAST (UTC+2) | Page {doc.page}")
        canvas.restoreState()

    story += [
        p("YOUR LEARNING JOURNEY", 10, True, BLUE),
        Spacer(1, 6),
        p(report["student"], 23, True, NAVY),
        Spacer(1, 6),
        p(f"{report['curriculum']} | {report['months']}-month subscription | R {report['amount']}"),
        p(f"{report['starts']} to {report['ends']}"),
        p(f"Prepared: {report['generated']} | {report['timezone']}"),
        p(f"Student email: {report['email']} | Subscription: {report['reference']}", 8),
        p(
            "Your next chapter: use your tutor's practice recommendations below to plan your learning. "
            "Contact the academy if any attendance details need correction.",
            8,
        ),
        p(f"Report ID: {report['report_id']}", 7),
        Spacer(1, 15),
    ]
    count = report["counts"]
    cards = Table(
        [
            [
                p(report["attended_label"], 17, True, BLUE),
                p(str(count["attended"] + count["partial"]), 17, True, BLUE),
                p(str(len(report["courses"])), 17, True, BLUE),
            ],
            [p("Confirmed attendance", 8), p("Sessions attended / partial", 8), p("Courses with activity", 8)],
        ],
        colWidths=[usable / 3] * 3,
    )
    cards.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef4ff")),
                ("TOPPADDING", (0, 0), (-1, 0), 12),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 12),
            ]
        )
    )
    story.append(cards)
    heading("01 / Your attendance at a glance")
    percentage = (
        "Not available: no confirmed attendance records"
        if report["attendance_percent"] is None
        else f"{report['attendance_percent']}% of confirmed scheduled minutes"
    )
    table(
        ["Measure", "Recorded result"],
        [
            ["Weekly plan", "Two 2-hour one-to-one Zoom sessions (4 hours per week)"],
            ["Scheduled time recorded", report["scheduled_label"]],
            ["Attendance percentage", percentage],
            ["Full / partial / missed", f"{count['attended']} / {count['partial']} / {count['absent']}"],
            ["Cancelled / attendance not recorded", f"{count['cancelled']} / {count['planned']}"],
        ],
        [usable * 0.42, usable * 0.58],
    )
    story += [
        Spacer(1, 9),
        p(report["scope_note"], 8),
        p(
            "Only sessions entered in the attendance ledger are counted. "
            "Partial weeks and unlogged sessions are not invented from the weekly plan.",
            8,
        ),
    ]
    if report["weeks"]:
        heading("02 / Weekly learning rhythm")
        table(
            ["Week beginning", "Scheduled hours", "Confirmed hours"],
            [
                [w["week"], f"{w['scheduled_minutes'] / 60:.2f}", f"{w['attended_minutes'] / 60:.2f}"]
                for w in report["weeks"]
            ],
            [usable / 3] * 3,
        )
    story.append(PageBreak())
    heading("03 / Session-by-session attendance")
    if not report["sessions"]:
        story.append(p("No subscription sessions were recorded for this period. This does not establish absence."))
    for row in report["sessions"]:
        title = p(f"{row['date']} | {row['topic']}", 10, True, NAVY)
        title.style.keepWithNext = True
        story += [
            Spacer(1, 10),
            title,
            p(f"Scheduled end: {row['end']} | Tutor: {row['tutor']}"),
            p(f"{row['subject']} | {row['level']} | {row['status']} | Confirmed minutes: {row['minutes']}"),
            p(f"Joined: {row['joined']} | Left: {row['left']}", 8),
        ]
        for key, label in [
            ("learning_summary", "Learning outcomes"),
            ("tutor_feedback", "Tutor feedback"),
            ("next_steps", "Practice and next steps"),
        ]:
            if row[key]:
                story.append(p(f"{label}: {row[key]}"))
    heading("04 / Course progress snapshot")
    story.append(
        p(
            "Latest recorded progress per course in this subscription. "
            "Percentages are student-reported progress, not examination results.",
            8,
        )
    )
    if report["courses"]:
        table(
            ["Course", "Last lesson", "Progress", "Last activity (SAST)"],
            [[c["course"], c["lesson"] or "Not recorded", f"{c['percent']}%", c["date"]] for c in report["courses"]],
            [usable * 0.29, usable * 0.29, usable * 0.13, usable * 0.29],
        )
    else:
        story.append(p("No course progress milestones were recorded during this period."))
    heading("05 / Dated course activity")
    if report["activities"]:
        table(
            ["Date and time (SAST)", "Course / lesson", "Milestone"],
            [
                [a["date"], f"{a['course']}\n{a['lesson']}", f"{a['action']}\n{a['percent']}%"]
                for a in report["activities"]
            ],
            [usable * 0.27, usable * 0.48, usable * 0.25],
        )
    else:
        story.append(p("No dated course activities available. Historical activity is not reconstructed."))
    SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=112,
        bottomMargin=60,
        title="Amaris student learning report",
        author="Amaris Mathematics Academy",
    ).build(story, onFirstPage=page, onLaterPages=page)
    return output.getvalue()
