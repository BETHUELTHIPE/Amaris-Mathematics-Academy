from __future__ import annotations

from unittest.mock import Mock, patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from amaris_cms.cache import ResilientRedisCache
from amaris_cms.middleware import PublicApiConditionalGetMiddleware


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


class ScopedRedisInvalidationTests(SimpleTestCase):
    def test_clear_does_not_flush_the_database_or_another_cache_alias(self):
        primary = ResilientRedisCache(
            "redis://localhost:6399/0",
            {"KEY_PREFIX": "amaris-public", "TIMEOUT": 30},
        )
        other = ResilientRedisCache(
            "redis://localhost:6399/0",
            {"KEY_PREFIX": "amaris-private", "TIMEOUT": 30},
        )
        primary._fallback_store.clear()
        primary._fallback_set("public-key", "public", timeout=30)
        other._fallback_set("payment-key", "payment", timeout=30)
        redis_client = Mock()
        redis_client.scan_iter.return_value = [
            b"amaris-public:1:public-key",
            b"amaris-private:1:payment-key",
            b"amaris-public-other:1:key",
        ]
        with patch.object(primary._cache, "get_client", return_value=redis_client):
            self.assertTrue(primary.clear())

        redis_client.flushdb.assert_not_called()
        redis_client.delete.assert_called_once_with(b"amaris-public:1:public-key")
        self.assertIsNone(primary._fallback_get("public-key"))
        self.assertEqual(other._fallback_get("payment-key"), "payment")
        other._fallback_store.clear()

    def test_authoritative_redis_miss_never_resurrects_stale_fallback(self):
        cache = ResilientRedisCache(
            "redis://localhost:6399/0",
            {"KEY_PREFIX": "amaris-public", "TIMEOUT": 30},
        )
        cache._fallback_store.clear()
        cache._fallback_set("deleted", "stale", timeout=30)
        cache._redis_retry_after = 0.0
        with patch("django.core.cache.backends.redis.RedisCache.get", return_value=None):
            self.assertIsNone(cache.get("deleted"))
        cache._fallback_store.clear()

    def test_clear_fails_closed_on_missing_namespace(self):
        cache = ResilientRedisCache("redis://localhost:6399/0", {"KEY_PREFIX": ""})
        with self.assertRaises(ValueError):
            cache.clear()


class PublicApiConditionalResponseTests(SimpleTestCase):
    def setUp(self):
        self.requests = RequestFactory()

    def response(self, *, cache_control="max-age=60"):
        response = HttpResponse(b'{"courses":[]}', content_type="application/json")
        response["Cache-Control"] = cache_control
        return response

    def test_public_anonymous_json_supports_etag_and_304(self):
        middleware = PublicApiConditionalGetMiddleware(lambda _request: self.response())
        first = middleware(self.requests.get("/api/v1/courses/"))
        self.assertEqual(first.status_code, 200)
        self.assertIn("public", first["Cache-Control"])
        self.assertTrue(first["ETag"].startswith('"'))
        second = middleware(self.requests.get("/api/v1/courses/", HTTP_IF_NONE_MATCH=first["ETag"]))
        self.assertEqual(second.status_code, 304)
        self.assertEqual(second.content, b"")

    def test_private_payment_route_is_not_modified(self):
        middleware = PublicApiConditionalGetMiddleware(lambda _request: self.response())
        result = middleware(self.requests.get("/api/v1/student/orders/"))
        self.assertNotIn("ETag", result)
        self.assertNotIn("public", result["Cache-Control"])

    def test_authorized_cookie_or_private_response_is_not_cached(self):
        middleware = PublicApiConditionalGetMiddleware(lambda _request: self.response())
        for request in (
            self.requests.get("/api/v1/courses/", HTTP_AUTHORIZATION="Bearer secret"),
            self.requests.get("/api/v1/courses/", HTTP_COOKIE="sessionid=private"),
        ):
            self.assertNotIn("ETag", middleware(request))
        private = PublicApiConditionalGetMiddleware(lambda _request: self.response(cache_control="private, no-store"))
        self.assertNotIn("ETag", private(self.requests.get("/api/v1/courses/")))
