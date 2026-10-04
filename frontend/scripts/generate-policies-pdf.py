"""Generate downloadable policy PDFs on the Amaris Mathematics Academy letterhead."""

import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    HRFlowable,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

ROOT = Path(__file__).resolve().parents[1]
POLICIES = json.loads((ROOT / "content/policies.json").read_text())
OUTPUT = ROOT / "public/policies"
OUTPUT.mkdir(parents=True, exist_ok=True)

NAVY = colors.HexColor("#0b2a5b")
BLUE = colors.HexColor("#0c79d8")
SKY = colors.HexColor("#68c4ff")
LIGHT_BLUE = colors.HexColor("#2e9eff")
INK = colors.HexColor("#0a1b36")
MUTED = colors.HexColor("#53647c")
GOLD = colors.HexColor("#c8912c")
BORDER = colors.HexColor("#dce4ef")

COMPANY_NAME = "Amaris Mathematics Academy"
TAGLINE = "Mathematics, taught with clarity."
MANAGING_DIRECTOR = "Bethuel Moukangwe - Managing Director & Head Tutor"
PHONE = "071 415 6665"
EMAIL = "bethuelmoukangwe8@gmail.com"
ADDRESS = "27 Tshivhase Street, Atteridgeville, Pretoria, Gauteng, 0008"
WEBSITE = "amaris-mathematics-academy-live-students.onrender.com"

label = ParagraphStyle(
    "Label", fontName="Helvetica-Bold", fontSize=8.7, leading=12,
    textColor=GOLD, spaceAfter=9,
)
title_style = ParagraphStyle(
    "Title", fontName="Helvetica-Bold", fontSize=20, leading=25,
    textColor=NAVY, spaceAfter=8,
)
summary_style = ParagraphStyle(
    "Summary", fontName="Helvetica", fontSize=9.8, leading=15,
    textColor=MUTED, spaceAfter=8,
)
date_style = ParagraphStyle(
    "Date", fontName="Helvetica", fontSize=8.3, leading=12,
    textColor=MUTED, spaceAfter=16,
)
heading_style = ParagraphStyle(
    "Heading", fontName="Helvetica-Bold", fontSize=11.5, leading=16,
    textColor=INK, spaceBefore=15, spaceAfter=7, keepWithNext=True,
)
body_style = ParagraphStyle(
    "Body", fontName="Helvetica", fontSize=8.8, leading=14.2,
    textColor=INK, spaceAfter=8,
)
bullet_style = ParagraphStyle(
    "Bullet", parent=body_style, leftIndent=0, firstLineIndent=0,
    spaceAfter=5,
)


def _draw_brand_mark(canvas, x, y, size=28):
    """Draw the academy's four-part blue mark from the public SVG geometry."""
    s = size / 24.0
    canvas.saveState()
    canvas.translate(x, y)
    canvas.setFillColor(LIGHT_BLUE)
    canvas.roundRect(0, 10 * s, 12 * s, 12 * s, 2.8 * s, fill=1, stroke=0)
    canvas.setFillColor(BLUE)
    canvas.roundRect(15 * s, 15 * s, 7 * s, 7 * s, 2 * s, fill=1, stroke=0)
    canvas.roundRect(2 * s, 0, 7 * s, 7 * s, 2 * s, fill=1, stroke=0)
    canvas.setFillColor(SKY)
    canvas.roundRect(12 * s, 0, 10 * s, 10 * s, 2.8 * s, fill=1, stroke=0)
    canvas.restoreState()


def page_letterhead(canvas, document):
    canvas.saveState()
    width, height = A4

    _draw_brand_mark(canvas, 47, height - 76, 30)
    canvas.setFillColor(NAVY)
    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawString(86, height - 54, COMPANY_NAME)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.4)
    canvas.drawString(86, height - 68, TAGLINE)
    canvas.drawString(86, height - 80, MANAGING_DIRECTOR)

    right_x = width - 47
    canvas.setFont("Helvetica", 7.1)
    canvas.setFillColor(INK)
    canvas.drawRightString(right_x, height - 50, f"Phone: {PHONE}")
    canvas.drawRightString(right_x, height - 61, f"Email: {EMAIL}")
    canvas.drawRightString(right_x, height - 72, WEBSITE)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 6.8)
    canvas.drawRightString(right_x, height - 83, ADDRESS)

    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(1.8)
    canvas.line(47, height - 96, width - 47, height - 96)
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(47, height - 100, width - 47, height - 100)

    canvas.setStrokeColor(BORDER)
    canvas.line(47, 41, width - 47, 41)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 6.7)
    canvas.drawString(47, 28, f"{COMPANY_NAME} | {PHONE} | {EMAIL}")
    canvas.drawRightString(width - 47, 28, f"Page {document.page}")
    canvas.restoreState()


for key, filename in (
    ("payment", "amaris-payment-policy.pdf"),
    ("working", "amaris-how-we-work-policy.pdf"),
):
    policy = POLICIES[key]
    path = OUTPUT / filename
    document = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=47,
        rightMargin=47,
        topMargin=116,
        bottomMargin=56,
        title=policy["title"],
        author=COMPANY_NAME,
        subject=f"{COMPANY_NAME} - {policy['title']}",
    )
    story = [
        Paragraph("OFFICIAL ACADEMY POLICY", label),
        Paragraph(escape(policy["title"]), title_style),
        Paragraph(escape(policy["summary"]), summary_style),
        Paragraph(f"Effective {escape(policy['effectiveDate'])}", date_style),
        HRFlowable(width="100%", thickness=0.8, color=BORDER),
        Spacer(1, 4),
    ]

    for number, section in enumerate(policy["sections"], start=1):
        story.append(Paragraph(f"{number}. {escape(section['heading'])}", heading_style))
        for block in section["blocks"]:
            if block["type"] == "paragraph":
                story.append(Paragraph(escape(block["text"]), body_style))
            else:
                story.append(
                    ListFlowable(
                        [ListItem(Paragraph(escape(item), bullet_style)) for item in block["items"]],
                        bulletType="bullet",
                        start="circle",
                        leftIndent=16,
                        bulletFontName="Helvetica",
                        bulletFontSize=7,
                    )
                )
                story.append(Spacer(1, 4))

    story.extend(
        [
            Spacer(1, 9),
            HRFlowable(width="100%", thickness=0.8, color=BORDER),
            Spacer(1, 8),
            Paragraph(
                "Questions? Use the Contact page on our website. Student Terms and Privacy Policy are also available there.",
                summary_style,
            ),
        ]
    )

    document.build(story, onFirstPage=page_letterhead, onLaterPages=page_letterhead)
    print(path)
