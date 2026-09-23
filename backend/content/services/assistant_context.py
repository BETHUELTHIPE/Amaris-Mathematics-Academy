import json

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from content.models import FAQ, Course, NavigationItem, Page, PageSection, PricingPlan, SiteSettings


def _live_filter():
    now = timezone.now()
    return Q(is_published=True) & (Q(publish_at__isnull=True) | Q(publish_at__lte=now))


def _clean(value: object, limit: int = 700) -> str:
    return " ".join(str(value or "").split())[:limit]


def _public_url(path: str) -> str:
    value = _clean(path, 320)
    if value.startswith(("https://", "http://")):
        return value

    base = _clean(getattr(settings, "PUBLIC_SITE_URL", ""), 260).rstrip("/")
    if not value.startswith("/"):
        value = f"/{value}"
    return f"{base}{value}" if base else value


def _structured_content(value: object, limit: int = 1400) -> str:
    if not value:
        return ""
    try:
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        rendered = str(value)
    return _clean(rendered, limit)


def build_website_context() -> str:
    site = SiteSettings.objects.first()
    lines: list[str] = []

    if site:
        lines.extend(
            [
                f"Academy: {_clean(site.site_name, 160)}",
                f"Phone: {_clean(site.phone, 80)}",
                f"Email: {_clean(site.email, 160)}",
                f"Address: {_clean(site.address, 260)}",
                f"Support hours: {_clean(site.business_hours, 160)}",
                f"Website: {_clean(getattr(settings, 'PUBLIC_SITE_URL', '') or site.website_url, 260)}",
                f"About: {_clean(site.footer_description, 500)}",
            ]
        )
    else:
        lines.extend(
            [
                "Academy: Amaris Mathematics Academy",
                f"Website: {_clean(getattr(settings, 'PUBLIC_SITE_URL', ''), 260)}",
                "Contact details are not available from published SiteSettings.",
            ]
        )

    lines.extend(
        [
            "\nOfficial website student workflow:",
            (
                f"- Course catalogue: {_public_url('/courses')}. Students can browse mathematics pathways for "
                "CAPS, IEB, TVET and University Modules."
            ),
            (
                f"- Registration: {_public_url('/register')}. A student creates a private learning profile before "
                "enrolling in a course."
            ),
            (
                f"- Email verification: {_public_url('/verify-email')}. After registration, the student verifies "
                "their email using either the six-digit verification code or the secure confirmation link sent in "
                "the same verification email."
            ),
            (
                f"- Login: {_public_url('/login')}. After email verification, the student logs in to access the "
                "private student dashboard."
            ),
            (
                "- Course selection and enrolment: open a course from the course catalogue. A visitor who is not "
                "verified is directed to registration; a verified student can continue to secure checkout."
            ),
            (
                f"- Secure checkout: {_public_url('/checkout/<course-slug>')}. Checkout is available to verified "
                "students, uses server-side course pricing, and continues to PayFast. Course access is activated "
                "only after the server verifies the PayFast notification."
            ),
            (
                f"- Student dashboard: {_public_url('/dashboard')}. After a verified payment activates access, the "
                "purchased course appears in the student's dashboard so they can start or continue learning."
            ),
            (
                f"- Password recovery: {_public_url('/forgot-password')}. The student enters their registration "
                "email and, if an account exists, receives a secure reset link."
            ),
        ]
    )

    navigation = NavigationItem.objects.filter(is_active=True).order_by("location", "order", "label")[:30]
    if navigation:
        lines.append("\nActive website navigation:")
        for item in navigation:
            lines.append(f"- {_clean(item.label, 100)}: {_public_url(item.url)}")

    courses = Course.objects.filter(_live_filter(), status=Course.Status.PUBLISHED).order_by("order", "title")[:24]
    if courses:
        lines.append("\nPublished courses:")
        for course in courses:
            lines.append(
                "- "
                + " | ".join(
                    [
                        _clean(course.title, 180),
                        f"curriculum={_clean(course.curriculum, 100)}",
                        f"level={_clean(course.academic_level, 100)}",
                        f"price=R{course.price}",
                        f"hours={course.estimated_hours}",
                        f"url={_public_url(f'/courses/{course.slug}')}",
                        _clean(course.short_description, 320),
                    ]
                )
            )

    pricing = PricingPlan.objects.filter(_live_filter()).order_by("order", "price")[:24]
    if pricing:
        lines.append("\nPublished pricing plans:")
        for plan in pricing:
            lines.append(
                "- "
                + " | ".join(
                    [
                        _clean(plan.name, 120),
                        f"price=R{plan.price}",
                        _clean(plan.billing_label, 100),
                        _clean(plan.description, 320),
                        "features=" + _clean(", ".join(str(item) for item in (plan.features or [])), 500),
                        (f"cta={_clean(plan.call_to_action_label, 100)} -> " f"{_public_url(plan.call_to_action_url)}"),
                    ]
                )
            )

    faqs = FAQ.objects.filter(_live_filter()).order_by("order", "question")[:40]
    if faqs:
        lines.append("\nPublished FAQs:")
        for faq in faqs:
            lines.append(f"- Q: {_clean(faq.question, 240)} | A: {_clean(faq.answer, 650)}")

    pages = Page.objects.filter(_live_filter()).order_by("title")[:16]
    if pages:
        lines.append("\nPublished website pages:")
        for page in pages:
            page_path = "/" if page.slug in {"home", "homepage"} else f"/{page.slug}"
            lines.append(f"- {_clean(page.title, 160)} | url={_public_url(page_path)}: {_clean(page.summary, 500)}")

    sections = (
        PageSection.objects.filter(_live_filter(), page__in=pages)
        .select_related("page")
        .order_by("page__title", "order")[:50]
    )
    if sections:
        lines.append("\nPublished page information:")
        for section in sections:
            details = [
                f"- {_clean(section.page.title, 120)} / {_clean(section.heading, 220)}: {_clean(section.body, 700)}"
            ]
            if section.call_to_action_label or section.call_to_action_url:
                details.append(
                    f"CTA={_clean(section.call_to_action_label, 100)} -> " f"{_public_url(section.call_to_action_url)}"
                )
            structured = _structured_content(section.content)
            if structured:
                details.append(f"structured_content={structured}")
            lines.append(" | ".join(details))

    return "\n".join(lines)[:28000]


def _extract_output_text(payload: dict) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    fragments: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if isinstance(content, dict) and content.get("type") == "output_text":
                value = content.get("text")
                if isinstance(value, str) and value.strip():
                    fragments.append(value.strip())
    return "\n".join(fragments).strip()
