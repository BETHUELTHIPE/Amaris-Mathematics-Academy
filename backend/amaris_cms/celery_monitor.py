"""Privacy-safe, read-only Celery/Redis snapshot for Django superusers.

Airflow monitors Airflow DAGs; Celery workers are monitored independently.
No task arguments, student data, exception messages or broker URLs are returned.
"""
from __future__ import annotations

import re

from django.conf import settings
from django.utils import timezone
from redis import Redis

from amaris_cms.celery import app as celery_app
from amaris_cms.celery_signals import DEAD_LETTER_KEY

QUEUE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
MAX_QUEUES = 8


def _queue_names() -> list[str]:
    configured = getattr(settings, "CELERY_MONITOR_QUEUES", ["default", "critical", "notifications"])
    return list(dict.fromkeys(name for name in configured if isinstance(name, str) and QUEUE_RE.fullmatch(name)))[:MAX_QUEUES]


def _registered_tasks() -> list[str]:
    # Names only; neither registered task signatures nor parameters are exposed.
    return sorted(
        name
        for name in celery_app.tasks
        if name.startswith(("content.tasks.", "amaris_cms.")) and len(name) <= 180
    )[:100]


def get_task_snapshot() -> dict:
    """Bounded monitoring snapshot. No network calls are made without a live broker."""
    result = {
        "checked_at": timezone.now().isoformat(),
        "state": "unavailable",
        "broker_online": False,
        "worker_count": 0,
        "worker_data_partial": False,
        "task_counts": {"active": 0, "reserved": 0, "scheduled": 0},
        "queue_depths": {},
        "failed_task_records": None,
        "registered_tasks": _registered_tasks(),
        "beat_schedule_count": len(getattr(settings, "CELERY_BEAT_SCHEDULE", {})),
        "beat_liveness_verified": False,
    }

    client = None
    try:
        client = Redis.from_url(
            settings.CELERY_BROKER_URL, socket_connect_timeout=1, socket_timeout=1
        )
        if not client.ping():
            return result
        result["broker_online"] = True
        for name in _queue_names():
            result["queue_depths"][name] = int(client.llen(name))
        result["failed_task_records"] = int(client.llen(DEAD_LETTER_KEY))
    except Exception:
        # Infrastructure details and authentication errors must never reach the UI.
        result["state"] = "unavailable"
        return result
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    try:
        inspector = celery_app.control.inspect(timeout=1.0)
        snapshots = {
            "active": inspector.active(),
            "reserved": inspector.reserved(),
            "scheduled": inspector.scheduled(),
        }
        workers = set()
        partial = False
        for state, payload in snapshots.items():
            if not isinstance(payload, dict):
                partial = True
                continue
            workers.update(payload.keys())
            result["task_counts"][state] = sum(
                len(tasks) for tasks in payload.values() if isinstance(tasks, list)
            )
        result["worker_count"] = len(workers)
        result["worker_data_partial"] = partial
        result["state"] = "healthy" if workers and not partial else "degraded"
    except Exception:
        # The broker can be healthy while workers are unreachable.
        result["state"] = "degraded"
        result["worker_data_partial"] = True
    return result
