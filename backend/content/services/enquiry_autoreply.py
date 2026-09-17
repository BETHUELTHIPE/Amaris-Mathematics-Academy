from __future__ import annotations

import os
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable
from urllib.parse import urljoin

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import get_connection
from django.db.models import Q
from django.utils import timezone

from content.models import ContactEnquiry, Course, FAQ, PricingPlan, SiteSettings

STOP_WORDS = {
    "about",
    "after",
    "again",
    "also",
    "and",
    "are",
    "can",
    "could",
    "for",
    "from",
    "have",
    "hello",
    "help",
    "how",
    "into",
    "like",
    "need",
    "please",
    "student",
    "that",
    "the",
    "their",
    "this",
    "want",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
    "your",
}
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+.#'-]{1,}", re.IGNORECASE)


@dataclass(frozen=True)
class ReplyItem:
    kind: str
    title: str
    body: str
    url: str = ""
    score: int = 0


def _live_q(now=None) -> Q:
    now = now or timezone.now()
    return Q(is_published=True) & (Q(publish_at__isnull=True) | Q(publish_at__lte=now))


def _tokens(value: str) -> set[str]:
    return {
        token.lower()
        for token in TOKEN_RE.findall(value or "")
        if len(token) >= 3 and token.lower() not in STOP_WORDS
    }


def _score(query_tokens: set[str], *values: object) -> int:
    candidate = _tokens(" ".join(str(value or "") for value in values))
    if not query_tokens or not candidate:
        return 0
    return len(query_tokens & candidate)


def _trim(value: str, limit: int = 520) -> str:
    normalized = " ".join((value or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _format_price(value: Decimal) -> str:
    return f"R{value:,.2f}"


def _absolute_url(base_url: str, path: str) -> str:
    base = (base_url or "").rstrip("/") + "/"
    return urljoin(base, path.lstrip("/")) if base.strip("/") else path


def _rank(items: Iterable[ReplyItem], limit: int) -> list[ReplyItem]:
    ranked = sorted(items, key=lambda item: (-item.score, item.kind, item.title.lower()))
    relevant = [item for item in ranked if item.score > 0]
    return relevant[:limit]


def build_enquiry_reply_context(enquiry: ContactEnquiry, *, max_items: int = 4) -> dict:
    """Build a reply exclusively from currently published website content."""

    now = timezone.now()
    site = SiteSettings.objects.first()
    site_name = site.site_name if site else "Amaris Mathematics Academy"
    website_url = site.website_url if site else ""
    query_tokens = _tokens(f"{enquiry.subject} {enquiry.message}")

    items: list[ReplyItem] = []

    for faq in FAQ.objects.filter(_live_q(now)).order_by("order", "question")[:80]:
        items.append(
            ReplyItem(
                kind="FAQ",
                title=faq.question,
                body=_trim(faq.answer),
                score=_score(query_tokens, faq.question, faq.answer, faq.category),
            )
        )

    for course in Course.objects.filter(
        _live_q(now), status=Course.Status.PUBLISHED
    ).select_related("category").order_by("order", "title")[:80]:
        body = _trim(
            f"{course.short_description} Curriculum: {course.curriculum}. "
            f"Level: {course.academic_level}. Price: {_format_price(course.price)}."
        )
        items.append(
            ReplyItem(
                kind="Course",
                title=course.title,
                body=body,
                url=_absolute_url(website_url, f"/courses/{course.slug}"),
                score=_score(
                    query_tokens,
                    course.title,
                    course.short_description,
                    course.description,
                    course.curriculum,
                    course.academic_level,
                    course.category.name,
                ),
            )
        )

    for plan in PricingPlan.objects.filter(_live_q(now)).order_by("order", "price")[:40]:
        features = ", ".join(str(feature) for feature in plan.features[:5])
        body = _trim(
            f"{plan.description} Price: {_format_price(plan.price)}"
            f"{f' {plan.billing_label}.' if plan.billing_label else '.'}"
            f"{f' Includes: {features}.' if features else ''}"
        )
        items.append(
            ReplyItem(
                kind="Pricing",
                title=plan.name,
                body=body,
                url=_absolute_url(website_url, plan.call_to_action_url or "/pricing"),
                score=_score(
                    query_tokens,
                    plan.name,
                    plan.description,
                    plan.billing_label,
                    features,
                    "price pricing cost fee fees package subscription payment",
                ),
            )
        )

    matched = _rank(items, max_items)

    # If there is no lexical match, acknowledge the enquiry without inventing an
    # answer. The human team can follow up while the email still gives official
    # contact details sourced from SiteSettings.
    return {
        "enquiry": enquiry,
        "site": site,
        "site_name": site_name,
        "website_url": website_url,
        "matched_items": matched,
        "has_answer": bool(matched),
    }


def contact_auto_reply_enabled() -> bool:
    return os.getenv("CONTACT_AUTO_REPLY_ENABLED", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def build_email_connection():
    """Create an email connection from runtime environment variables.

    Production defaults to SMTP and fails closed if credentials are missing.
    Development defaults to the console backend so local work never sends mail
    accidentally.
    """

    backend = os.getenv("EMAIL_BACKEND", "").strip()
    if not backend:
        backend = (
            "django.core.mail.backends.console.EmailBackend"
            if settings.DEBUG
            else "django.core.mail.backends.smtp.EmailBackend"
        )

    if backend != "django.core.mail.backends.smtp.EmailBackend":
        return get_connection(backend=backend)

    host = os.getenv("EMAIL_HOST", "").strip()
    username = os.getenv("EMAIL_HOST_USER", "").strip()
    password = os.getenv("EMAIL_HOST_PASSWORD", "")
    if not host or not username or not password:
        raise ImproperlyConfigured(
            "SMTP auto-replies require EMAIL_HOST, EMAIL_HOST_USER, and EMAIL_HOST_PASSWORD."
        )

    return get_connection(
        backend=backend,
        host=host,
        port=int(os.getenv("EMAIL_PORT", "587")),
        username=username,
        password=password,
        use_tls=os.getenv("EMAIL_USE_TLS", "true").strip().lower() in {"1", "true", "yes", "on"},
        use_ssl=os.getenv("EMAIL_USE_SSL", "false").strip().lower() in {"1", "true", "yes", "on"},
        timeout=int(os.getenv("EMAIL_TIMEOUT_SECONDS", "20")),
    )


def default_from_email(site: SiteSettings | None) -> str:
    return (
        os.getenv("DEFAULT_FROM_EMAIL", "").strip()
        or os.getenv("EMAIL_HOST_USER", "").strip()
        or (site.email if site else "")
    )
