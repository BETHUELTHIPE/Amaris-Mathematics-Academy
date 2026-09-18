import json
import logging
import re
import uuid

from django.conf import settings
from django.core.cache import cache
from django.utils.deprecation import MiddlewareMixin

from amaris_cms.incidents import build_incident

CORRELATION_PATTERN = re.compile(r"^AMR-[A-Za-z0-9-]{8,64}$")
incident_logger = logging.getLogger("amaris.incident")


class CorrelationReferenceMiddleware:
    """Attach an opaque support reference without including personal data."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get("X-Correlation-ID", "")
        reference = (
            incoming
            if CORRELATION_PATTERN.fullmatch(incoming)
            else f"AMR-{uuid.uuid4().hex[:16].upper()}"
        )
        request.correlation_reference = reference
        response = self.get_response(request)
        response["X-Correlation-ID"] = reference
        return response


class ProductionIncidentMiddleware(MiddlewareMixin):
    """Capture unhandled exceptions without collecting request secrets or PII."""

    def process_exception(self, request, exception):
        incident = build_incident(request, exception)
        incident_logger.error(
            json.dumps(
                {"production_incident": incident},
                separators=(",", ":"),
                sort_keys=True,
            )
        )

        if not settings.INCIDENT_AUTOMATION_ENABLED:
            return None

        dedupe_key = f"production-incident:{incident['fingerprint']}"
        try:
            if cache.add(
                dedupe_key,
                "1",
                timeout=settings.INCIDENT_DEDUP_SECONDS,
            ):
                from content.tasks import dispatch_production_incident

                dispatch_production_incident.delay(incident)
        except Exception:
            # Failure to enqueue an incident must never replace the original
            # application exception or leak request data into a secondary error.
            incident_logger.error(
                "production incident automation enqueue failed",
                exc_info=True,
            )
        return None
