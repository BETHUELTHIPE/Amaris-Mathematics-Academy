import hashlib
import re

from django.utils.cache import get_conditional_response, patch_cache_control
from django.utils.http import quote_etag
import uuid

CORRELATION_PATTERN = re.compile(r"^AMR-[A-Za-z0-9-]{8,64}$")


class CorrelationReferenceMiddleware:
    """Attach an opaque support reference without including personal data."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get("X-Correlation-ID", "")
        reference = incoming if CORRELATION_PATTERN.fullmatch(incoming) else f"AMR-{uuid.uuid4().hex[:16].upper()}"
        request.correlation_reference = reference
        response = self.get_response(request)
        response["X-Correlation-ID"] = reference
        return response


class PublicApiConditionalGetMiddleware:
    """Strong ETags/304 only for anonymous, read-only, explicitly public CMS JSON.

    Private student, tutor, payment and administrative URLs never receive
    public cache headers or conditional responses from this middleware.
    """

    PUBLIC_PATHS = frozenset(
        {
            "/api/v1/bootstrap/",
            "/api/v1/announcements/",
            "/api/v1/courses/",
            "/api/v1/faqs/",
            "/api/v1/navigation/",
            "/api/v1/pricing-plans/",
            "/api/v1/course-categories/",
            "/api/v1/testimonials/",
        }
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            request.method != "GET"
            or request.path_info not in self.PUBLIC_PATHS
            or request.headers.get("Authorization")
            or request.COOKIES
            or response.status_code != 200
            or response.streaming
            or response.has_header("Set-Cookie")
            or not response.get("Content-Type", "").lower().startswith("application/json")
        ):
            return response

        cache_control = response.get("Cache-Control", "").lower()
        vary = response.get("Vary", "").lower()
        if any(flag in cache_control for flag in ("private", "no-cache", "no-store")) or "cookie" in vary:
            return response

        # ETag is a hash of precisely this public JSON response, not a token,
        # account identifier or database object revision.
        etag = quote_etag(hashlib.sha256(response.content).hexdigest())
        patch_cache_control(response, public=True)
        response["ETag"] = etag
        if request.headers.get("If-None-Match"):
            return get_conditional_response(request, etag=etag, response=response)
        return response
