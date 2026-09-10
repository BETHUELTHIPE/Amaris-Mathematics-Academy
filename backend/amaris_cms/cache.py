import logging

from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.core.cache.backends.redis import RedisCache
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class ResilientRedisCache(RedisCache):
    """Treat cache outages as misses so Redis never becomes a platform dependency."""

    _cache_errors = (RedisError, OSError, ConnectionError)
    _warned_operations: set[str] = set()

    def _warn_once(self, operation: str, message: str) -> None:
        if operation not in self._warned_operations:
            logger.warning(message)
            self._warned_operations.add(operation)

    def get(self, key, default=None, version=None):
        try:
            return super().get(key, default=default, version=version)
        except self._cache_errors:
            self._warn_once("read", "Cache read failed; continuing without cached data.")
            return default

    def set(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        try:
            return super().set(key, value, timeout=timeout, version=version)
        except self._cache_errors:
            self._warn_once("write", "Cache write failed; response was not cached.")
            return None

    def clear(self):
        try:
            return super().clear()
        except self._cache_errors:
            self._warn_once("clear", "Cache invalidation was delayed because Redis is unavailable.")
            return False
