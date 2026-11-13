"""Professional Amaris letterhead for every outgoing Django communication.

Matches frontend/components/documents/brand-letterhead.tsx. All dynamic
user-supplied copy is autoescaped by the Django template; no HTML fragments
are accepted from AI replies, student fields or payment data.
"""

from __future__ import annotations

from email.mime.image import MIMEImage
from pathlib import Path

from django.template.loader import render_to_string

from content.models import SiteSettings

DEFAULT_NAME = "Amaris Mathematics Academy"
DEFAULT_EMAIL = "bethuelmoukangwe8@gmail.com"
DEFAULT_PHONE = "071 415 6665"
DEFAULT_ADDRESS = "27 Tshivhase Street, Atteridgeville, Pretoria, Gauteng, 0008"


def render_branded_email(
    heading: str,
    lines: list[str] | tuple[str, ...],
    *,
    reference: str = "",
) -> str:
    """Return HTML body while retaining the caller's independent text fallback."""
    site = SiteSettings.objects.first()
    return render_to_string(
        "emails/amaris_letterhead.html",
        {
            "academy_name": (site.site_name if site and site.site_name else DEFAULT_NAME),
            "email": (site.email if site and site.email else DEFAULT_EMAIL),
            "phone": (site.phone if site and site.phone else DEFAULT_PHONE),
            "address": (site.address if site and site.address else DEFAULT_ADDRESS),
            "heading": str(heading),
            "lines": [str(line) for line in lines],
            "reference": str(reference),
        },
    )


def apply_letterhead(message, heading, lines, *, reference=""):
    """Retain plain text, recipients, headers and attachments; replace HTML with the approved letterhead."""
    message.alternatives = [item for item in message.alternatives if item[1] != "text/html"]
    message.attach_alternative(render_branded_email(heading, lines, reference=reference), "text/html")
    if not any(
        hasattr(part, "get") and part.get("Content-ID") == "<amaris-letterhead-logo>" for part in message.attachments
    ):
        asset = Path(__file__).resolve().parents[1] / "static" / "invoice-brand" / "amaris-academy-icon-192.png"
        logo = MIMEImage(asset.read_bytes(), _subtype="png")
        logo.add_header("Content-ID", "<amaris-letterhead-logo>")
        logo.add_header("Content-Disposition", "inline", filename="amaris-academy-icon-192.png")
        message.attach(logo)
    return message
