"""A repeatable company-letterhead PDF; uses approved invoice fonts and logo."""

from io import BytesIO

from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Spacer

from content.models import SiteSettings
from content.services.invoice_document import (
    BLUE,
    CONTENT_WIDTH,
    GOLD,
    HEIGHT,
    MARGIN,
    NAVY,
    WIDTH,
    _logo,
    _paragraph,
    _register_fonts,
)
from content.services.performance_metrics import report_sections


def render_performance_pdf(snapshot, reference):
    _register_fonts()
    site = SiteSettings.objects.first() or SiteSettings()
    logo = _logo(site)
    output = BytesIO()

    def letterhead(page, doc):
        page.saveState()
        page.setTitle("Amaris fortnightly performance report")
        page.setAuthor(site.site_name)
        for x, fraction, colour in ((0, 0.58, NAVY), (WIDTH * 0.58, 0.24, BLUE), (WIDTH * 0.82, 0.18, GOLD)):
            page.setFillColor(colour)
            page.rect(x, HEIGHT - 5, WIDTH * fraction, 5, fill=1, stroke=0)
        page.drawImage(logo, MARGIN, HEIGHT - 88, width=56, height=56, preserveAspectRatio=True, mask="auto")
        for text, y, size in [
            (site.site_name, HEIGHT - 39, 16),
            ("MATHEMATICS · LEARNING · PROGRESS", HEIGHT - 61, 8),
            (f"Managing Director: {site.managing_director}", HEIGHT - 79, 8),
        ]:
            paragraph = _paragraph(text, size=size, color=NAVY)
            _, height = paragraph.wrap(CONTENT_WIDTH - 80, 60)
            paragraph.drawOn(page, MARGIN + 72, y - height)
        contacts = _paragraph(f"{site.phone} · {site.email}\n{site.address}", size=7)
        _, height = contacts.wrap(CONTENT_WIDTH, 50)
        contacts.drawOn(page, MARGIN, HEIGHT - 108 - height)
        page.setStrokeColor(GOLD)
        page.line(MARGIN, 65, WIDTH - MARGIN, 65)
        footer = _paragraph(
            f"Confidential Admin report · {site.site_name}\nReference: {reference} · Page {doc.page}", size=7
        )
        footer.wrap(CONTENT_WIDTH, 35)
        footer.drawOn(page, MARGIN, 30)
        page.restoreState()

    document = BaseDocTemplate(output, pagesize=(WIDTH, HEIGHT))
    document.addPageTemplates(
        PageTemplate(
            id="academy",
            frames=[Frame(MARGIN, 80, CONTENT_WIDTH, HEIGHT - 245, leftPadding=0, rightPadding=0)],
            onPage=letterhead,
        )
    )
    story = [_paragraph("Fortnightly performance review", size=18, color=NAVY, bold=True), Spacer(1, 15)]
    for heading, lines in report_sections(snapshot):
        title = _paragraph(heading, size=12, color=BLUE, bold=True)
        title.keepWithNext = True
        spacing = Spacer(1, 6)
        spacing.keepWithNext = True
        story.extend([title, spacing])
        for line in lines:
            story.extend([_paragraph(line, size=9), Spacer(1, 8)])
        story.append(Spacer(1, 8))
    document.build(story)
    return output.getvalue()
