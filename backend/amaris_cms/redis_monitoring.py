"""Bounded, read-only Redis/Valkey health snapshots for Django superusers.

Only allowlisted aggregate INFO fields are returned. Never return Redis URLs,
credentials, keys, values, client addresses, configuration or raw exceptions.
"""

from django.conf import settings
from redis import Redis
from redis.exceptions import RedisError

SOCKET_TIMEOUT_SECONDS = 1.0


def _safe_int(value):
    try:
        return max(int(value), 0)
    except (TypeError, ValueError, OverflowError):
        return 0


def _snapshot(url):
    if not isinstance(url, str) or not url.startswith(("redis://", "rediss://")):
        return {"available": False, "status": "Not configured", "stats": {}}

    client = None
    try:
        client = Redis.from_url(
            url,
            socket_connect_timeout=SOCKET_TIMEOUT_SECONDS,
            socket_timeout=SOCKET_TIMEOUT_SECONDS,
            retry_on_timeout=False,
        )
        if not client.ping():
            raise RedisError("Unhealthy Redis connection")

        # Allowlisted INFO sections only, not CLIENT LIST, KEYS, GET, CONFIG,
        # ACL, MONITOR, or data-modifying commands.
        info = {}
        for section in ("server", "memory", "clients", "stats"):
            section_data = client.info(section=section)
            if isinstance(section_data, dict):
                info.update(section_data)

        used_memory = _safe_int(info.get("used_memory"))
        max_memory = _safe_int(info.get("maxmemory"))
        hits = _safe_int(info.get("keyspace_hits"))
        misses = _safe_int(info.get("keyspace_misses"))
        return {
            "available": True,
            "status": "Connected",
            "stats": {
                "memory_mib": round(used_memory / (1024 * 1024), 1),
                "max_memory_mib": round(max_memory / (1024 * 1024), 1) if max_memory else None,
                "memory_percent": round(used_memory * 100 / max_memory, 1) if max_memory else None,
                "connected_clients": _safe_int(info.get("connected_clients")),
                "blocked_clients": _safe_int(info.get("blocked_clients")),
                "ops_per_sec": _safe_int(info.get("instantaneous_ops_per_sec")),
                "uptime_hours": round(_safe_int(info.get("uptime_in_seconds")) / 3600, 1),
                "cache_hits": hits,
                "cache_misses": misses,
                "hit_rate": round(hits * 100 / (hits + misses), 1) if (hits + misses) else None,
                "evicted_keys": _safe_int(info.get("evicted_keys")),
                "expired_keys": _safe_int(info.get("expired_keys")),
            },
        }
    except (RedisError, OSError, ValueError, TypeError):
        # Fail closed without exposing hostnames, usernames or passwords.
        return {"available": False, "status": "Unavailable", "stats": {}}
    finally:
        if client is not None:
            client.close()


def get_redis_snapshots():
    """Query only app-configured Redis endpoints, never a browser-supplied URL."""
    endpoints = (
        ("Celery broker", getattr(settings, "CELERY_BROKER_URL", "")),
        ("Celery results", getattr(settings, "CELERY_RESULT_BACKEND", "")),
        ("Django cache", settings.CACHES.get("default", {}).get("LOCATION", "")),
        ("Public content cache", settings.CACHES.get("public_content", {}).get("LOCATION", "")),
    )
    return [
        {"name": name, **_snapshot(url)}
        for name, url in endpoints
    ]
