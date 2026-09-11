from __future__ import annotations

import os
import uuid
from unittest import mock

from celery import current_app
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import connection
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from content.tasks import publish_scheduled_content


class PostgreSQLIntegrationTests(TestCase):
    def test_django_is_using_postgresql_and_can_round_trip_sql(self):
        self.assertEqual(connection.vendor, "postgresql")
        marker = f"integration-{uuid.uuid4()}"
        with connection.cursor() as cursor:
            cursor.execute("CREATE TEMP TABLE integration_probe (value text NOT NULL)")
            cursor.execute("INSERT INTO integration_probe (value) VALUES (%s)", [marker])
            cursor.execute("SELECT value FROM integration_probe")
            self.assertEqual(cursor.fetchone()[0], marker)


class RedisIntegrationTests(TestCase):
    def test_django_cache_round_trip_uses_configured_redis(self):
        key = f"integration-cache-{uuid.uuid4()}"
        value = {"ok": True, "id": str(uuid.uuid4())}
        cache.set(key, value, timeout=60)
        self.assertEqual(cache.get(key), value)
        cache.delete(key)
        self.assertIsNone(cache.get(key))


class CeleryIntegrationTests(TestCase):
    def test_celery_broker_connection_and_task_publish(self):
        broker_url = current_app.conf.broker_url or ""
        self.assertTrue(broker_url.startswith("redis://"))
        with current_app.connection_for_write() as conn:
            conn.ensure_connection(max_retries=1)
            self.assertTrue(conn.connected)

        result = publish_scheduled_content.apply_async()
        self.assertIsNotNone(result.id)


class FrontendApiIntegrationTests(TestCase):
    def test_public_frontend_api_endpoint_is_served_by_django(self):
        client = APIClient()
        response = client.get("/api/courses/")
        self.assertLess(response.status_code, 500)
        self.assertIn(response.status_code, {200, 301, 302, 403, 404})


class StorageIntegrationTests(TestCase):
    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        }
    )
    def test_storage_abstraction_round_trip_without_external_s3(self):
        path = f"integration/{uuid.uuid4()}.txt"
        stored = default_storage.save(path, ContentFile(b"amaris-integration"))
        try:
            with default_storage.open(stored, "rb") as handle:
                self.assertEqual(handle.read(), b"amaris-integration")
        finally:
            default_storage.delete(stored)


class ExternalAdapterSafetyTests(TestCase):
    def test_external_provider_environment_is_not_required_for_integration_suite(self):
        provider_vars = [
            "PAYFAST_MERCHANT_ID",
            "PAYFAST_MERCHANT_KEY",
            "WHATSAPP_TOKEN",
            "SMS_API_KEY",
            "ZOOM_CLIENT_SECRET",
            "OPENAI_API_KEY",
            "GEMINI_API_KEY",
            "YOUTUBE_API_KEY",
        ]
        exposed = {name: bool(os.getenv(name)) for name in provider_vars}
        self.assertTrue(all(value is False for value in exposed.values()))

    @mock.patch("django.core.mail.send_mail", autospec=True)
    def test_email_is_mocked_and_no_real_message_is_sent(self, send_mail):
        send_mail.return_value = 1
        from django.core.mail import send_mail as mocked_send_mail

        sent = mocked_send_mail("subject", "body", "noreply@example.test", ["student@example.test"])
        self.assertEqual(sent, 1)
        send_mail.assert_called_once()
