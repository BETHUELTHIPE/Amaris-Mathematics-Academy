import logging
import threading
import time
from collections import OrderedDict

from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.core.cache.backends.redis import RedisCache
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class ResilientRedisCache(RedisCache):
    """Use Redis first and bounded process-local TTL storage as outage fallback."""

    _cache_errors = (RedisError, OSError, ConnectionError)
    _warned_operations: set[str] = set()
    _fallback_lock = threading.RLock()
    _fallback_store: "OrderedDict[str, tuple[float | None, object]]" = OrderedDict()
    _fallback_max_entries = 512

    def _warn_once(self, operation: str, message: str) -> None:
        if operation not in self._warned_operations:
            logger.warning(message)
            self._warned_operations.add(operation)

    def _fallback_key(self, key, version=None) -> str:
        return self.make_key(key, version=version)

    def _fallback_get(self, key, default=None, version=None):
        cache_key = self._fallback_key(key, version=version)
        now = time.monotonic()
        with self._fallback_lock:
            item = self._fallback_store.get(cache_key)
            if item is None:
                return default
            expires_at, value = item
            if expires_at is not None and expires_at <= now:
                self._fallback_store.pop(cache_key, None)
                return default
            self._fallback_store.move_to_end(cache_key)
            return value

    def _fallback_set(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        cache_key = self._fallback_key(key, version=version)
        resolved_timeout = self.get_backend_timeout(timeout)
        if resolved_timeout == 0:
            return False

        if resolved_timeout is None:
            expires_at = None
        else:
            expires_at = time.monotonic() + max(0.0, float(resolved_timeout))

        with self._fallback_lock:
            self._fallback_store[cache_key] = (expires_at, value)
            self._fallback_store.move_to_end(cache_key)
            while len(self._fallback_store) > self._fallback_max_entries:
                self._fallback_store.popitem(last=False)
        return True

    def get(self, key, default=None, version=None):
        try:
            value = super().get(key, default=None, version=version)
        except self._cache_errors:
            self._warn_once(
                "read",
                "Redis cache read failed; using bounded local fallback cache.",
            )
            return self._fallback_get(key, default=default, version=version)

        if value is None:
            return self._fallback_get(key, default=default, version=version)
        return value

    def set(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        fallback_result = self._fallback_set(
            key,
            value,
            timeout=timeout,
            version=version,
        )
        try:
            return super().set(key, value, timeout=timeout, version=version)
        except self._cache_errors:
            self._warn_once(
                "write",
                "Redis cache write failed; response retained in bounded local fallback cache.",
            )
            return fallback_result

    def clear(self):
        with self._fallback_lock:
            self._fallback_store.clear()
        try:
            return super().clear()
        except self._cache_errors:
            self._warn_once(
                "clear",
                "Redis cache invalidation was unavailable; local fallback cache was cleared.",
            )
            return True
