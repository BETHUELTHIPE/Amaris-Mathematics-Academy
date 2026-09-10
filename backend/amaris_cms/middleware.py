import re
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
