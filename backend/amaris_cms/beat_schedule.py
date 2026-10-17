"""Bounded, explicitly routed recurring jobs for the single Celery Beat service.

These jobs poll durable PostgreSQL records. A queued invocation can expire safely:
the next tick will inspect the same records. This prevents an overloaded broker
from accumulating redundant polling requests while preserving the work itself.
"""

from typing import Any


def build_beat_schedule(*, include_reconciliation: bool = True) -> dict[str, dict[str, Any]]:
    schedule: dict[str, dict[str, Any]] = {
        "publish-scheduled-content": {
            "task": "content.tasks.publish_scheduled_content",
            "schedule": 60.0,
            "options": {"queue": "default", "expires": 55},
        },
        "deliver-transactional-email": {
            "task": "content.tasks.deliver_transactional_email",
            "schedule": 30.0,
            "options": {"queue": "notifications", "expires": 28},
        },
        "deliver-live-class-confirmation": {
            "task": "content.tasks.deliver_live_class_confirmation",
            "schedule": 30.0,
            "options": {"queue": "notifications", "expires": 28},
        },
        "deliver-live-class-reminder": {
            "task": "content.tasks.deliver_live_class_reminder",
            "schedule": 60.0,
            "options": {"queue": "notifications", "expires": 55},
        },
        "expire-live-class-holds": {
            "task": "content.tasks.expire_live_class_holds",
            "schedule": 300.0,
            "options": {"queue": "critical", "expires": 270},
        },
    }
    if include_reconciliation:
        schedule["reconcile-verified-payments"] = {
            "task": "content.tasks.reconcile_payments",
            "schedule": 300.0,
            "options": {"queue": "critical", "expires": 270},
        }
    return schedule
