from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import Any

from prometheus_client import Counter, Histogram

PAYMENT_WEBHOOK_EVENTS = Counter(
    "amaris_payment_webhook_events_total",
    "Server-side payment webhook processing outcomes.",
    ("provider", "outcome"),
)
PAYMENT_WEBHOOK_DURATION = Histogram(
    "amaris_payment_webhook_duration_seconds",
    "Server-side payment webhook verification and processing latency.",
    ("provider",),
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10),
)


def observe_payment_webhook(provider: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(function: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(function)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            started = time.monotonic()
            try:
                result = function(*args, **kwargs)
            except Exception:
                PAYMENT_WEBHOOK_EVENTS.labels(provider=provider, outcome="exception").inc()
                raise
            finally:
                PAYMENT_WEBHOOK_DURATION.labels(provider=provider).observe(time.monotonic() - started)

            if getattr(result, "accepted", False):
                outcome = "accepted"
            elif getattr(result, "retryable", False):
                outcome = "retryable"
            else:
                outcome = "rejected"
            PAYMENT_WEBHOOK_EVENTS.labels(provider=provider, outcome=outcome).inc()
            return result

        return wrapper

    return decorator
