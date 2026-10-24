"""Read-only Django Admin Redis/Valkey dashboard security and contract tests."""

from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse

from amaris_cms.monitoring_admin import AmarisAdminSite
from amaris_cms.redis_monitoring import get_redis_snapshots


class RedisAdminTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.site = AmarisAdminSite()
        self.superuser = SimpleNamespace(
            is_authenticated=True,
            is_active=True,
            is_staff=True,
            is_superuser=True,
        )
        self.staff = SimpleNamespace(
            is_authenticated=True,
            is_active=True,
            is_staff=True,
            is_superuser=False,
        )

    def test_named_admin_url(self):
        self.assertEqual(reverse("admin:amaris_redis_monitor"), "/admin/monitoring/redis/")

    @patch("amaris_cms.monitoring_admin.get_redis_snapshots")
    def test_non_superuser_cannot_read_redis_metrics(self, collector):
        request = self.factory.get("/admin/monitoring/redis/")
        request.user = self.staff
        with self.assertRaises(PermissionDenied):
            self.site.redis_home(request)
        collector.assert_not_called()

    @patch("amaris_cms.monitoring_admin.get_redis_snapshots")
    def test_only_get_is_supported(self, collector):
        request = self.factory.post("/admin/monitoring/redis/", {"command": "FLUSHALL"})
        request.user = self.superuser
        response = self.site.redis_home(request)
        self.assertEqual(response.status_code, 405)
        collector.assert_not_called()

    @override_settings(
        CELERY_BROKER_URL="redis://:very-secret@redis-private:6379/0",
        CELERY_RESULT_BACKEND="redis://:very-secret@redis-private:6379/1",
        CACHES={
            "default": {"LOCATION": "redis://:very-secret@redis-private:6379/2"},
            "public_content": {"LOCATION": "redis://:very-secret@redis-private:6379/3"},
        },
    )
    @patch("amaris_cms.redis_monitoring.Redis.from_url")
    def test_whitelisted_metrics_and_secret_redaction(self, client_factory):
        client = client_factory.return_value
        client.ping.return_value = True
        sections = {
            "server": {"uptime_in_seconds": 3600, "redis_version": "8.0.0", "config_file": "/secret/path"},
            "memory": {"used_memory": 1048576, "maxmemory": 4194304},
            "clients": {"connected_clients": 4, "blocked_clients": 0, "client_addr": "private-address"},
            "stats": {
                "instantaneous_ops_per_sec": 12,
                "keyspace_hits": 9,
                "keyspace_misses": 1,
                "evicted_keys": 2,
                "expired_keys": 3,
            },
        }
        client.info.side_effect = lambda section: sections[section]

        snapshots = get_redis_snapshots()
        self.assertEqual(len(snapshots), 4)
        self.assertTrue(all(snapshot["available"] for snapshot in snapshots))
        self.assertEqual(snapshots[0]["stats"]["memory_mib"], 1.0)
        self.assertEqual(snapshots[0]["stats"]["memory_percent"], 25.0)
        self.assertEqual(snapshots[0]["stats"]["hit_rate"], 90.0)
        self.assertEqual(
            {call.kwargs["section"] for call in client.info.call_args_list},
            {"server", "memory", "clients", "stats"},
        )

        request = self.factory.get("/admin/monitoring/redis/")
        request.user = self.superuser
        response = self.site.redis_home(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        response.render()
        page = response.content.decode()
        self.assertIn("Celery broker", page)
        self.assertIn("Commands / second", page)
        for secret in ("very-secret", "redis-private", "/secret/path", "private-address"):
            self.assertNotIn(secret, page)
            self.assertNotIn(secret, str(snapshots))
        self.assertEqual(client.close.call_count, 8)

    @override_settings(
        CELERY_BROKER_URL="redis://:redacted@private-host:6379/0",
        CELERY_RESULT_BACKEND="not-a-redis-url",
        CACHES={"default": {}, "public_content": {}},
    )
    @patch("amaris_cms.redis_monitoring.Redis.from_url")
    def test_unavailable_and_unconfigured_do_not_reveal_credentials(self, client_factory):
        client_factory.side_effect = OSError("secret hostname: private-host")
        snapshots = get_redis_snapshots()
        self.assertEqual(snapshots[0]["status"], "Unavailable")
        self.assertEqual(snapshots[1]["status"], "Not configured")
        self.assertEqual(snapshots[2]["status"], "Not configured")
        self.assertNotIn("private-host", str(snapshots))
        self.assertNotIn("redacted", str(snapshots))
        self.assertEqual(client_factory.call_count, 1)
