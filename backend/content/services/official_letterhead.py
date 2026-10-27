"""Existing Amaris letterhead, adapted for formal HTML email communications.

Matches the frontend BrandLetterhead / BrandDocumentFooter: academy logo,
name, tagline, approved CMS contact information, address, website, gold accent
and a document reference. Never interpolate untrusted content without escaping.
"""

from __future__ import annotations

from html import escape
from urllib.parse import urlsplit

from django.conf import settings

from content.models import SiteSettings

DEFAULT_SITE_URL = "https://amaris-mathematics-academy-live-students.onrender.com"
DEFAULT_ADDRESS = "27 Tshivhase Street, Atteridgeville, Pretoria, Gauteng, 0008"


def _safe_site_url() -> str:
    site_url = str(getattr(settings, "PUBLIC_SITE_URL", "") or DEFAULT_SITE_URL).rstrip("/")
    parts = urlsplit(site_url)
    return site_url if parts.scheme == "https" and parts.netloc else DEFAULT_SITE_URL


def official_letterhead_html(
    *,
    heading: str,
    body_lines: list[str],
    reference: str = "",
    site: SiteSettings | None = None,
) -> str:
    """Render a legible, escaped formal email inside the existing letterhead."""

    if site is None:
        site = SiteSettings.objects.first()
    name = str(site.site_name if site and site.site_name else "Amaris Mathematics Academy")
    email = str(site.email if site and site.email else "bethuelmoukangwe8@gmail.com")
    phone = str(site.phone if site and site.phone else "071 415 6665")
    address = str(site.address if site and site.address else DEFAULT_ADDRESS)
    url = _safe_site_url()

    def e(value: object) -> str:
        return escape(str(value), quote=True)

    body = "".join(
        (
            f'<p style="margin:0 0 14px;line-height:1.7;overflow-wrap:anywhere">{e(line)}</p>'
            if line
            else '<div style="height:8px"></div>'
        )
        for line in body_lines
    )
    reference_html = (
        f'<p style="font-size:12px;color:#60708a;margin-top:18px">Reference: {e(reference)}</p>' if reference else ""
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"></head>'
        '<body style="margin:0;padding:24px;background:#f5f7fb;color:#263852;font-family:Arial,Helvetica,sans-serif">'
        '<table role="presentation" cellpadding="0" cellspacing="0" style="max-width:660px;width:100%;margin:auto;'
        'background:#fff;border:1px solid #dce4ef;border-radius:16px;overflow:hidden">'
        '<tr><td style="height:7px;background:#ffcc66"></td></tr>'
        '<tr><td style="padding:22px 28px 14px">'
        f'<img src="{e(url)}/brand/amaris-academy-icon-192.png" alt="{e(name)} logo" '
        'width="64" height="64" style="vertical-align:middle;display:inline-block;margin-right:16px">'
        f'<span style="color:#07152d;font-size:22px;font-weight:bold;vertical-align:middle">{e(name)}</span>'
        '<div style="font-size:11px;letter-spacing:1px;color:#1f5bbd;margin-top:12px">'
        'MATHEMATICS · LEARNING · PROGRESS</div></td></tr>'
        '<tr><td style="padding:12px 28px;background:#f6f8fc;border-top:1px solid #dce4ef;'
        'border-bottom:1px solid #dce4ef;color:#43526a;font-size:12px;line-height:1.7">'
        f'<strong>Cell:</strong> {e(phone)} &nbsp; <strong>Email:</strong> {e(email)}<br>'
        f'<strong>Address:</strong> {e(address)}<br><strong>Web:</strong> {e(url)}'
        '</td></tr>'
        '<tr><td style="padding:28px">'
        f'<h1 style="font-size:22px;color:#07152d;margin:0 0 22px">{e(heading)}</h1>'
        f'{body}{reference_html}</td></tr>'
        '<tr><td style="padding:16px 28px;border-top:2px solid #ffcc66;color:#60708a;font-size:11px;line-height:1.7">'
        f'{e(name)} · {e(address)}<br>{e(phone)} · {e(email)}<br>'
        'Professional mathematics education and learner support</td></tr>'
        '</table></body></html>'
    )
