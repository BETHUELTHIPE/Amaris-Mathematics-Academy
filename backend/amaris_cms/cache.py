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
    _redis_retry_after = 0.0
    _redis_retry_seconds = 15.0

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
        resolved_timeout = self.default_timeout if timeout is DEFAULT_TIMEOUT else timeout
        if resolved_timeout is not None and float(resolved_timeout) <= 0:
            return False

        if resolved_timeout is None:
            expires_at = None
        else:
            expires_at = time.monotonic() + float(resolved_timeout)

        with self._fallback_lock:
            self._fallback_store[cache_key] = (expires_at, value)
            self._fallback_store.move_to_end(cache_key)
            while len(self._fallback_store) > self._fallback_max_entries:
                self._fallback_store.popitem(last=False)
        return True

    def _redis_available_for_attempt(self) -> bool:
        return time.monotonic() >= self._redis_retry_after

    def _open_redis_circuit(self) -> None:
        self._redis_retry_after = time.monotonic() + self._redis_retry_seconds

    def _close_redis_circuit(self) -> None:
        self._redis_retry_after = 0.0

    def get(self, key, default=None, version=None):
        if not self._redis_available_for_attempt():
            return self._fallback_get(key, default=default, version=version)

        try:
            value = super().get(key, default=None, version=version)
            self._close_redis_circuit()
        except self._cache_errors:
            self._open_redis_circuit()
            self._warn_once(
                "read",
                "Redis cache read failed; using bounded local fallback cache.",
            )
            return self._fallback_get(key, default=default, version=version)

        # A successful Redis miss is authoritative. Returning a process-local
        # fallback entry here could resurrect stale public data after another
        # worker invalidated the Redis namespace.
        return default if value is None else value

    def set(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        fallback_result = self._fallback_set(
            key,
            value,
            timeout=timeout,
            version=version,
        )
        if not self._redis_available_for_attempt():
            return fallback_result

        try:
            result = super().set(key, value, timeout=timeout, version=version)
            self._close_redis_circuit()
            return result
        except self._cache_errors:
            self._open_redis_circuit()
            self._warn_once(
                "write",
                "Redis cache write failed; response retained in bounded local fallback cache.",
            )
            return fallback_result

    def clear(self):
        """Invalidate only this cache alias, never FLUSHDB a shared Redis database.

        Django's RedisCache.clear() flushes the entire selected Redis DB, even
        if KEY_PREFIX differs. Content updates must not clear session or other
        aliases that might be configured on the same Redis database.
        """
        if not self.key_prefix:
            raise ValueError("Cache invalidation requires a nonempty KEY_PREFIX.")

        # The standard Django key function creates <prefix>:<version>:<key>.
        # Match the entire namespace (including the colon) to avoid deleting
        # similar prefixes or keys with other versions.
        namespace = self.make_key("")
        if not namespace.startswith(f"{self.key_prefix}:") or not namespace.endswith(":"):
            raise ValueError("Unsupported cache key function for scoped invalidation.")

        with self._fallback_lock:
            for key in tuple(self._fallback_store):
                if key.startswith(namespace):
                    self._fallback_store.pop(key, None)

        # Redis glob characters may be present in a configured KEY_PREFIX.
        # Escape them to prevent the scan from expanding beyond the alias.
        pattern = "".join(("\\" + char) if char in "*?[]\\" else char for char in namespace) + "*"
        try:
            client = getattr(self, "_cache").get_client(write=True)
            batch = []
            namespace_bytes = namespace.encode("utf-8")
            for key in client.scan_iter(match=pattern, count=100):
                if not (key.startswith(namespace_bytes) if isinstance(key, bytes) else key.startswith(namespace)):
                    continue
                batch.append(key)
                if len(batch) >= 100:
                    client.delete(*batch)
                    batch.clear()
            if batch:
                client.delete(*batch)
            return True
        except self._cache_errors:
            self._warn_once(
                "clear",
                "Scoped Redis cache invalidation failed; only this alias's local fallback entries were cleared.",
            )
            return False
