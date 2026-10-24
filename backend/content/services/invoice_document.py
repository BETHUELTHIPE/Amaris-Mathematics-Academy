"""The PDF equivalent of the academy's approved InvoiceDocument letterhead.

Every paid service uses this renderer for its email attachment and private
archive. Keep the visual system aligned with frontend/components/documents.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Literal
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    LongTable,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from content.models import SiteSettings

ASSETS = Path(__file__).resolve().parents[1] / "static" / "invoice-brand"
NAVY = colors.HexColor("#07152d")
BLUE = colors.HexColor("#1f5bbd")
SLATE = colors.HexColor("#60708a")
LINE = colors.HexColor("#dce4ef")
GOLD = colors.HexColor("#ffcc66")
WIDTH, HEIGHT = A4
MARGIN = 40
CONTENT_WIDTH = WIDTH - MARGIN * 2


@dataclass(frozen=True)
class InvoiceLine:
    description: str
    details: tuple[str, ...]
    quantity: Decimal
    unit_price: Decimal

    @property
    def amount(self) -> Decimal:
        return self.quantity * self.unit_price


@dataclass(frozen=True)
class InvoiceDocument:
    number: str
    issue_date: str
    student_name: str
    student_email: str
    reference: str
    currency: str
    lines: tuple[InvoiceLine, ...]
    total: Decimal
    status: Literal["Paid", "Template"] = "Paid"


@lru_cache(maxsize=1)
def _register_fonts() -> None:
    for name, filename in (("AmarisSans", "DejaVuSans.ttf"), ("AmarisSans-Bold", "DejaVuSans-Bold.ttf")):
        pdfmetrics.registerFont(TTFont(name, str(ASSETS / filename)))
    pdfmetrics.registerFontFamily("AmarisSans", normal="AmarisSans", bold="AmarisSans-Bold")


def _paragraph(text: object, *, size: float = 9, color=SLATE, bold: bool = False, right: bool = False) -> Paragraph:
    # Model text must never be interpreted as ReportLab markup or file links.
    style = ParagraphStyle(
        "invoice",
        fontName="AmarisSans-Bold" if bold else "AmarisSans",
        fontSize=size,
        leading=size * 1.5,
        textColor=color,
        alignment=TA_RIGHT if right else 0,
        splitLongWords=True,
    )
    return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)


def _money(value: Decimal) -> str:
    return f"R {value:,.2f}"


def _logo(site: SiteSettings) -> ImageReader:
    if site.logo:
        try:
            with site.logo.open("rb") as logo:
                reader = ImageReader(BytesIO(logo.read()))
                reader.getSize()
                return reader
        except Exception:
            pass
    # This is the same checked-in logo used by BrandLetterhead; an empty
    # SiteSettings table must not produce an invoice without the academy logo.
    return ImageReader(str(ASSETS / "amaris-academy-icon-192.png"))


def render_document(document: InvoiceDocument) -> bytes:
    """Render the approved A4 invoice with a repeated letterhead and footer."""
    if document.currency != "ZAR" or not document.lines or document.total < 0:
        raise ValueError("Invalid invoice currency, items or total.")
    if any(line.quantity <= 0 or line.unit_price < 0 for line in document.lines):
        raise ValueError("Invoice quantities and prices must be valid.")
    if sum((line.amount for line in document.lines), Decimal("0")) != document.total:
        raise ValueError("Invoice line items do not match its verified total.")
    _register_fonts()
    site = SiteSettings.objects.first() or SiteSettings()
    logo = _logo(site)
    contacts = [
        _paragraph(f"Cell: {site.phone}", size=6.5),
        _paragraph(f"Email: {site.email}", size=6.5),
        _paragraph(f"Address: {site.address}", size=6.5),
        _paragraph(
            "Web:\n" + site.website_url.removeprefix("https://").removeprefix("http://").replace(".", ".\n", 1),
            size=6.5,
        ),
    ]
    contact_band = Table([contacts], colWidths=[CONTENT_WIDTH / 4] * 4)
    contact_band.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f6f8fc")),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LINEABOVE", (0, 0), (-1, -1), 0.5, LINE),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
            ]
        )
    )
    _, band_height = contact_band.wrap(CONTENT_WIDTH, HEIGHT)
    body_top = HEIGHT - 108 - band_height - 15

    def letterhead(page, doc):
        page.saveState()
        page.setTitle(f"Invoice {document.number}")
        page.setAuthor(site.site_name)
        for x, fraction, color in ((0, 0.58, NAVY), (WIDTH * 0.58, 0.24, BLUE), (WIDTH * 0.82, 0.18, GOLD)):
            page.setFillColor(color)
            page.rect(x, HEIGHT - 5, WIDTH * fraction, 5, fill=1, stroke=0)
        page.setFillColor(colors.white)
        page.setStrokeColor(LINE)
        page.roundRect(MARGIN, HEIGHT - 88, 62, 62, 10, fill=1, stroke=1)
        page.drawImage(logo, MARGIN + 5, HEIGHT - 83, width=52, height=52, preserveAspectRatio=True, mask="auto")
        heading = _paragraph(site.site_name, size=15, color=NAVY, bold=True)
        _, heading_height = heading.wrap(CONTENT_WIDTH - 145, 48)
        heading.drawOn(page, MARGIN + 76, HEIGHT - 32 - heading_height)
        tagline = _paragraph("MATHEMATICS · LEARNING · PROGRESS", size=7, color=BLUE, bold=True)
        tagline.wrap(CONTENT_WIDTH - 145, 20)
        tagline.drawOn(page, MARGIN + 76, HEIGHT - 65)
        director = _paragraph(f"Managing Director: {site.managing_director}", size=7)
        director.wrap(CONTENT_WIDTH - 145, 20)
        director.drawOn(page, MARGIN + 76, HEIGHT - 82)
        page.setFillColor(colors.HexColor("#edf3ff"))
        page.roundRect(WIDTH - MARGIN - 60, HEIGHT - 70, 60, 24, 12, fill=1, stroke=0)
        page.setFillColor(BLUE)
        page.setFont("AmarisSans-Bold", 7)
        page.drawCentredString(WIDTH - MARGIN - 30, HEIGHT - 61, "INVOICE")
        contact_band.drawOn(page, MARGIN, HEIGHT - 108 - band_height)
        page.setStrokeColor(GOLD)
        page.setLineWidth(1.5)
        page.line(MARGIN, 64, WIDTH - MARGIN, 64)
        footer = _paragraph(f"{site.site_name} · {site.address}", size=6.2)
        footer.wrap(CONTENT_WIDTH, 24)
        footer.drawOn(page, MARGIN, 46)
        page.setFont("AmarisSans", 6.2)
        page.setFillColor(SLATE)
        page.drawString(MARGIN, 33, f"{site.phone} · {site.email}")
        reference = _paragraph(f"Reference: {document.number} · Page {doc.page}", size=6.2, color=NAVY, right=True)
        reference.wrap(CONTENT_WIDTH / 2, 24)
        reference.drawOn(page, WIDTH / 2, 17)
        page.drawString(MARGIN, 17, "Professional mathematics education and learner support")
        page.restoreState()

    billed_to = [
        _paragraph("BILLED TO", size=8, color=BLUE, bold=True),
        Spacer(1, 8),
        _paragraph(document.student_name, size=12, color=NAVY, bold=True),
        _paragraph(document.student_email, size=8),
    ]
    metadata = Table(
        [
            [_paragraph(label, size=7.5), _paragraph(value, size=7.5, color=NAVY, bold=True, right=True)]
            for label, value in (
                ("Invoice number", document.number),
                ("Issue date", document.issue_date),
                ("Currency", document.currency),
                ("Status", "Paid - server verified" if document.status == "Paid" else "Preview - not issued"),
            )
        ],
        colWidths=[80, CONTENT_WIDTH / 2 - 80],
    )
    metadata.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    billing = Table([[billed_to, metadata]], colWidths=[CONTENT_WIDTH / 2] * 2)
    billing.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 15),
            ]
        )
    )
    rows = [
        [
            _paragraph(label, size=8, color=colors.white, bold=True, right=index > 0)
            for index, label in enumerate(("Description", "Qty", "Unit price", "Amount"))
        ]
    ]
    for line in document.lines:
        rows.append(
            [
                [
                    _paragraph(line.description, size=9, color=NAVY, bold=True),
                    Spacer(1, 4),
                    *[_paragraph(detail, size=7.5) for detail in line.details],
                ],
                _paragraph(f"{line.quantity:g}", size=8, color=NAVY, right=True),
                _paragraph(_money(line.unit_price), size=8, color=NAVY, right=True),
                _paragraph(_money(line.amount), size=8, color=NAVY, bold=True, right=True),
            ]
        )
    items = LongTable(rows, colWidths=[CONTENT_WIDTH - 195, 30, 82, 83], repeatRows=1, splitInRow=1)
    items.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    items.setStyle(TableStyle([("LEFTPADDING", (1, 0), (1, -1), 3), ("RIGHTPADDING", (1, 0), (1, -1), 3)]))
    totals = Table(
        [
            [_paragraph("Subtotal", size=8), _paragraph(_money(document.total), size=8, right=True)],
            [_paragraph("Tax", size=7), _paragraph("Included where applicable", size=6.5, right=True)],
            [
                _paragraph("Total", size=12, color=NAVY, bold=True),
                _paragraph(_money(document.total), size=12, color=NAVY, bold=True, right=True),
            ],
        ],
        colWidths=[70, 145],
        hAlign="RIGHT",
    )
    totals.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f5f7fb")),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LINEABOVE", (0, 2), (-1, 2), 0.5, LINE),
            ]
        )
    )
    notes = Table(
        [
            [
                [
                    _paragraph("PAYMENT NOTE", size=8, color=BLUE, bold=True),
                    Spacer(1, 7),
                    _paragraph(
                        (
                            "Payment verified through PayFast. "
                            "Your invoice is linked to the verified payment reference below."
                            if document.status == "Paid"
                            else "SAMPLE - NOT ISSUED. This preview is not a payment receipt."
                        ),
                        size=7.5,
                    ),
                    Spacer(1, 7),
                    _paragraph(f"Payment reference: {document.reference}", size=7),
                ],
                [
                    _paragraph("NEED HELP?", size=8, color=colors.HexColor("#8a6000"), bold=True),
                    Spacer(1, 7),
                    _paragraph(
                        "Contact Amaris and include the invoice number shown above so we can assist you quickly.",
                        size=7.5,
                    ),
                ],
            ]
        ],
        colWidths=[CONTENT_WIDTH * 0.58, CONTENT_WIDTH * 0.42],
    )
    notes.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (0, 0), 0.5, LINE),
                ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#fff7df")),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    output = BytesIO()
    pdf = BaseDocTemplate(output, pagesize=A4, pageCompression=1, invariant=1)
    pdf.addPageTemplates(
        PageTemplate(
            id="academy-invoice",
            frames=[
                Frame(
                    MARGIN,
                    76,
                    CONTENT_WIDTH,
                    body_top - 76,
                    leftPadding=0,
                    rightPadding=0,
                    topPadding=0,
                    bottomPadding=0,
                )
            ],
            onPage=letterhead,
        )
    )
    pdf.build(
        [billing, Spacer(1, 22), items, Spacer(1, 18), KeepTogether([totals, Spacer(1, 22), notes])],
        canvasmaker=canvas.Canvas,
    )
    return output.getvalue()
