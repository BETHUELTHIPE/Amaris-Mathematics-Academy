"""Professional Amaris letterhead for every outgoing Django communication.

Matches frontend/components/documents/brand-letterhead.tsx. All dynamic
user-supplied copy is autoescaped by the Django template; no HTML fragments
are accepted from AI replies, student fields or payment data.
"""
from __future__ import annotations

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
