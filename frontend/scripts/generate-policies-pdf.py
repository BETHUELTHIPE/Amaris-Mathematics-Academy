"""Generate the downloadable policy PDFs from the same JSON used by the pages."""

import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
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

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
pdfmetrics.registerFont(TTFont("DejaVu", str(FONT_DIR / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(FONT_DIR / "DejaVuSans-Bold.ttf")))

NAVY = colors.HexColor("#0b2a5b")
INK = colors.HexColor("#0a1b36")
MUTED = colors.HexColor("#53647c")
GOLD = colors.HexColor("#c8912c")

label = ParagraphStyle("Label", fontName="DejaVu-Bold", fontSize=9, leading=13, textColor=GOLD, spaceAfter=10)
title_style = ParagraphStyle("Title", fontName="DejaVu-Bold", fontSize=21, leading=27, textColor=NAVY, spaceAfter=9)
summary_style = ParagraphStyle("Summary", fontName="DejaVu", fontSize=10, leading=16, textColor=MUTED, spaceAfter=8)
date_style = ParagraphStyle("Date", fontName="DejaVu", fontSize=8.5, leading=13, textColor=MUTED, spaceAfter=18)
heading_style = ParagraphStyle("Heading", fontName="DejaVu-Bold", fontSize=12, leading=17, textColor=INK, spaceBefore=17, spaceAfter=8, keepWithNext=True)
body_style = ParagraphStyle("Body", fontName="DejaVu", fontSize=9, leading=15, textColor=INK, spaceAfter=9)
bullet_style = ParagraphStyle("Bullet", parent=body_style, leftIndent=0, firstLineIndent=0, spaceAfter=6)


def page_chrome(canvas, document):
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(colors.HexColor("#dce4ef"))
    canvas.line(47, height - 39, width - 47, height - 39)
    canvas.setFont("DejaVu", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(47, 29, "Amaris Mathematics Academy  |  amaris-mathematics-academy-live-students.onrender.com")
    canvas.drawRightString(width - 47, 29, str(document.page))
    canvas.restoreState()


for key, filename in (
    ("payment", "amaris-payment-policy.pdf"),
    ("working", "amaris-how-we-work-policy.pdf"),
):
    policy = POLICIES[key]
    path = OUTPUT / filename
    document = SimpleDocTemplate(
        str(path), pagesize=A4, leftMargin=47, rightMargin=47,
        topMargin=58, bottomMargin=50, title=policy["title"],
        author="Amaris Mathematics Academy",
    )
    story = [
        Paragraph("AMARIS MATHEMATICS ACADEMY", label),
        Paragraph(escape(policy["title"]), title_style),
        Paragraph(escape(policy["summary"]), summary_style),
        Paragraph(f"Effective {escape(policy['effectiveDate'])}", date_style),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#dce4ef")),
        Spacer(1, 5),
    ]
    for number, section in enumerate(policy["sections"], start=1):
        story.append(Paragraph(f"{number}. {escape(section['heading'])}", heading_style))
        for block in section["blocks"]:
            if block["type"] == "paragraph":
                story.append(Paragraph(escape(block["text"]), body_style))
            else:
                story.append(ListFlowable(
                    [ListItem(Paragraph(escape(item), bullet_style)) for item in block["items"]],
                    bulletType="bullet", start="circle", leftIndent=16,
                    bulletFontName="DejaVu", bulletFontSize=7,
                ))
                story.append(Spacer(1, 5))
    story.extend([
        Spacer(1, 10),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#dce4ef")),
        Spacer(1, 9),
        Paragraph("Questions? Visit the Contact page on our website. Student Terms and Privacy Policy are also available there.", summary_style),
    ])
    document.build(story, onFirstPage=page_chrome, onLaterPages=page_chrome)
    print(path)
