from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from celery.signals import task_failure
from django.conf import settings
from redis import Redis
from redis.exceptions import RedisError

LOGGER = logging.getLogger(__name__)
DEAD_LETTER_KEY = "amaris:celery:dead-letter"
DEAD_LETTER_MAX_ITEMS = 1000


@task_failure.connect
def park_failed_task(sender=None, task_id=None, exception=None, **_kwargs) -> None:
    """Persist sanitized metadata for terminal task failures.

    Task arguments are deliberately excluded so student or payment data cannot be
    copied into operational queues. Intermediate Celery retries emit retry events;
    task_failure is used for the terminal failed state.
    """

    payload = {
        "task_id": str(task_id or ""),
        "task": getattr(sender, "name", "unknown"),
        "error_type": exception.__class__.__name__ if exception is not None else "UnknownError",
        "failed_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        client = Redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=2, socket_timeout=2)
        pipeline = client.pipeline()
        pipeline.lpush(DEAD_LETTER_KEY, json.dumps(payload, separators=(",", ":")))
        pipeline.ltrim(DEAD_LETTER_KEY, 0, DEAD_LETTER_MAX_ITEMS - 1)
        pipeline.execute()
        client.close()
    except (RedisError, OSError, ConnectionError):
        LOGGER.exception("Unable to persist Celery dead-letter metadata for task %s", payload["task"])
