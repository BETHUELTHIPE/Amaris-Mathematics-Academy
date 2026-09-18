from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from amaris_cms.cache import ResilientRedisCache


class ResilientRedisFallbackTests(SimpleTestCase):
    def make_cache(self):
        cache = ResilientRedisCache(
            "redis://127.0.0.1:6399/15",
            {
                "TIMEOUT": 5,
                "KEY_PREFIX": "test-fallback",
                "OPTIONS": {
                    "socket_connect_timeout": 0.01,
                    "socket_timeout": 0.01,
                },
            },
        )
        cache._fallback_store.clear()
        cache._redis_retry_after = 0.0
        return cache

    def test_fallback_round_trip_when_redis_is_unavailable(self):
        cache = self.make_cache()
        with patch(
            "django.core.cache.backends.redis.RedisCache.set",
            side_effect=OSError("synthetic redis outage"),
        ):
            self.assertTrue(cache.set("course-list", {"ok": True}, timeout=30))

        with patch(
            "django.core.cache.backends.redis.RedisCache.get",
            side_effect=OSError("synthetic redis outage"),
        ):
            self.assertEqual(cache.get("course-list"), {"ok": True})

    def test_redis_circuit_skips_repeated_failed_network_attempts(self):
        cache = self.make_cache()
        with patch(
            "django.core.cache.backends.redis.RedisCache.get",
            side_effect=OSError("synthetic redis outage"),
        ) as redis_get:
            self.assertIsNone(cache.get("missing"))
            self.assertIsNone(cache.get("missing"))
        self.assertEqual(redis_get.call_count, 1)

    def test_redis_circuit_retries_after_cooldown(self):
        cache = self.make_cache()
        cache._redis_retry_seconds = 15
        with (
            patch("amaris_cms.cache.time.monotonic", side_effect=[100.0, 100.0, 100.5, 116.0, 116.0, 116.5]),
            patch(
                "django.core.cache.backends.redis.RedisCache.get",
                side_effect=OSError("synthetic redis outage"),
            ) as redis_get,
        ):
            self.assertIsNone(cache.get("missing"))
            self.assertIsNone(cache.get("missing"))
        self.assertEqual(redis_get.call_count, 2)

    def test_fallback_entry_expires_using_duration_semantics(self):
        cache = self.make_cache()
        with patch("amaris_cms.cache.time.monotonic", side_effect=[100.0, 100.5, 101.1]):
            cache._fallback_set("short", "value", timeout=1)
            self.assertEqual(cache._fallback_get("short"), "value")
            self.assertIsNone(cache._fallback_get("short"))

    def test_zero_timeout_is_not_cached(self):
        cache = self.make_cache()
        self.assertFalse(cache._fallback_set("zero", "value", timeout=0))
        self.assertIsNone(cache._fallback_get("zero"))

    def test_fallback_is_bounded_lru(self):
        cache = self.make_cache()
        original_limit = cache._fallback_max_entries
        try:
            cache._fallback_max_entries = 2
            cache._fallback_set("one", 1, timeout=30)
            cache._fallback_set("two", 2, timeout=30)
            self.assertEqual(cache._fallback_get("one"), 1)
            cache._fallback_set("three", 3, timeout=30)
            self.assertEqual(cache._fallback_get("one"), 1)
            self.assertIsNone(cache._fallback_get("two"))
            self.assertEqual(cache._fallback_get("three"), 3)
        finally:
            cache._fallback_max_entries = original_limit
            cache._fallback_store.clear()
