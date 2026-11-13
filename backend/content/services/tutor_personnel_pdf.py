"""A4 personnel forms using the academy's existing document letterhead assets."""

from io import BytesIO

from reportlab.lib import colors
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Spacer

from content.models import SiteSettings
from content.services.invoice_document import (
    BLUE,
    CONTENT_WIDTH,
    GOLD,
    HEIGHT,
    LINE,
    MARGIN,
    NAVY,
    WIDTH,
    _logo,
    _paragraph,
    _register_fonts,
)


def form_lines(item):
    p = item.payload
    lines = [
        ("Tutor", p["tutor_name"]),
        ("Tutor email", p["tutor_email"]),
        ("Submitted", p["submitted_at"]),
        ("Submission status", "Submitted for Admin review"),
    ]
    if item.kind == "leave":
        lines += [
            ("Leave type", p["leave_type_label"]),
            ("First day of leave", p["start_date"]),
            ("Last day of leave", p["end_date"]),
            ("Calendar days requested (inclusive)", p["calendar_days"]),
        ]
    else:
        lines += [("Proposed last teaching day", p["last_teaching_day"])]
    lines += [
        ("Reason", p["reason"]),
        ("Affected lessons and handover plan", p["handover"]),
        ("Contact number", p["contact_phone"]),
        ("Typed signature", p["signature_name"]),
        (
            "Declaration",
            "I confirm these details are accurate and submit this form to Amaris Mathematics Academy for review.",
        ),
        (
            "Review process",
            "Leave requires Admin approval. A resignation notice requires academy follow-up. "
            "Submission does not cancel lessons or change account access.",
        ),
    ]
    return lines


def render_personnel_form(item):
    _register_fonts()
    site = SiteSettings.objects.first() or SiteSettings()
    logo = _logo(site)
    output = BytesIO()

    def letterhead(page, doc):
        page.saveState()
        page.setTitle(f"{item.get_kind_display()} - {item.pk}")
        page.setAuthor(site.site_name)
        for x, fraction, color in ((0, 0.58, NAVY), (WIDTH * 0.58, 0.24, BLUE), (WIDTH * 0.82, 0.18, GOLD)):
            page.setFillColor(color)
            page.rect(x, HEIGHT - 5, WIDTH * fraction, 5, fill=1, stroke=0)
        page.drawImage(logo, MARGIN, HEIGHT - 88, width=56, height=56, preserveAspectRatio=True, mask="auto")
        for text, y, size, color in [
            (site.site_name, HEIGHT - 39, 16, NAVY),
            ("MATHEMATICS · LEARNING · PROGRESS", HEIGHT - 61, 8, BLUE),
            (f"Managing Director: {site.managing_director}", HEIGHT - 79, 8, NAVY),
        ]:
            paragraph = _paragraph(text, size=size, color=color)
            _, height = paragraph.wrap(CONTENT_WIDTH - 80, 60)
            paragraph.drawOn(page, MARGIN + 72, y - height)
        contacts = _paragraph(f"{site.phone} · {site.email}\n{site.address}", size=7)
        _, height = contacts.wrap(CONTENT_WIDTH, 50)
        contacts.drawOn(page, MARGIN, HEIGHT - 108 - height)
        page.setStrokeColor(LINE)
        page.line(MARGIN, HEIGHT - 152, WIDTH - MARGIN, HEIGHT - 152)
        page.setStrokeColor(GOLD)
        page.line(MARGIN, 63, WIDTH - MARGIN, 63)
        footer = _paragraph(
            f"{site.site_name} · Confidential tutor personnel record\nReference: {item.pk} · Page {doc.page}", size=7
        )
        footer.wrap(CONTENT_WIDTH, 35)
        footer.drawOn(page, MARGIN, 29)
        page.restoreState()

    document = BaseDocTemplate(output, pagesize=(WIDTH, HEIGHT))
    document.addPageTemplates(
        PageTemplate(
            id="academy",
            frames=[Frame(MARGIN, 78, CONTENT_WIDTH, HEIGHT - 245, leftPadding=0, rightPadding=0)],
            onPage=letterhead,
        )
    )
    story = [_paragraph(item.get_kind_display(), size=18, color=NAVY, bold=True), Spacer(1, 15)]
    for label, value in form_lines(item):
        heading = _paragraph(label.upper(), size=8, color=BLUE, bold=True)
        heading.keepWithNext = True
        story.extend([heading, _paragraph(value, size=9, color=colors.HexColor("#263852")), Spacer(1, 10)])
    document.build(story)
    return output.getvalue()
