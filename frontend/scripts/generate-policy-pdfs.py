"""Regenerate downloadable policies from the same content used by the website.

Run with the backend virtualenv's Python after installing backend/requirements.txt.
"""

import json
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

FRONTEND = Path(__file__).resolve().parents[1]
POLICIES = json.loads((FRONTEND / "lib" / "policies.json").read_text(encoding="utf-8"))
OUTPUT = FRONTEND / "public" / "policies"
OUTPUT.mkdir(parents=True, exist_ok=True)


def make_footer(canvas, document):
    canvas.saveState()
    width, _ = A4
    canvas.setStrokeColor(colors.HexColor("#dce4ef"))
    canvas.line(48, 53, width - 48, 53)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#60708a"))
    canvas.drawString(48, 39, "Amaris Mathematics Academy  |  bethuelmoukangwe8@gmail.com  |  071 415 6665")
    canvas.drawRightString(width - 48, 39, str(document.page))
    canvas.restoreState()


styles = {
    "brand": ParagraphStyle("brand", fontName="Helvetica-Bold", fontSize=11, leading=16, textColor=colors.HexColor("#1f5bbd")),
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=23, leading=30, spaceAfter=10, textColor=colors.HexColor("#07152d")),
    "meta": ParagraphStyle("meta", fontName="Helvetica", fontSize=9, leading=14, spaceAfter=17, textColor=colors.HexColor("#60708a")),
    "intro": ParagraphStyle("intro", fontName="Helvetica", fontSize=11, leading=17, spaceAfter=13, textColor=colors.HexColor("#263a55")),
    "heading": ParagraphStyle("heading", fontName="Helvetica-Bold", fontSize=12, leading=17, spaceBefore=12, spaceAfter=5, keepWithNext=True, textColor=colors.HexColor("#07152d")),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=10, leading=15, spaceAfter=4, textColor=colors.HexColor("#34445c")),
}

for kind, policy in POLICIES.items():
    output = OUTPUT / f"{kind}-policy.pdf"
    document = SimpleDocTemplate(
        str(output), pagesize=A4, leftMargin=48, rightMargin=48,
        topMargin=50, bottomMargin=72, title=policy["title"],
        author="Amaris Mathematics Academy",
    )
    story = [
        Paragraph("AMARIS MATHEMATICS ACADEMY", styles["brand"]),
        Spacer(1, 9),
        Paragraph(escape(policy["title"]), styles["title"]),
        Paragraph(f"Effective {escape(policy['effective'])}", styles["meta"]),
        Paragraph(escape(policy["intro"]), styles["intro"]),
    ]
    for section in policy["sections"]:
        story.append(Paragraph(escape(section["title"]), styles["heading"]))
        story.append(Paragraph(escape(section["body"]), styles["body"]))
    document.build(story, onFirstPage=make_footer, onLaterPages=make_footer)
    print(output)
