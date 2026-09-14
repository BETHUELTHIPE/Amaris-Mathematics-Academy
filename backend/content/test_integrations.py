from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from celery.contrib.testing.worker import start_worker
from django.conf import settings
from django.core import mail
from django.core.cache import caches
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.core.mail import send_mail
from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from redis import Redis
from redis.exceptions import RedisError

from amaris_cms.celery import app as celery_app
from content.models import Course, CourseCategory, NavigationItem, SiteSettings


def _is_ci() -> bool:
    return os.getenv("GITHUB_ACTIONS", "").strip().lower() == "true"


def _require_or_skip(test_case, condition: bool, message: str) -> None:
    if condition:
        return
    if _is_ci():
        test_case.fail(message)
    test_case.skipTest(message)


def _redis_url(database: int) -> str:
    source = settings.CELERY_BROKER_URL
    parsed = urlsplit(source)
    return urlunsplit((parsed.scheme, parsed.netloc, f"/{database}", "", ""))


def _redis_client(test_case, url: str) -> Redis:
    client = Redis.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    try:
        connected = bool(client.ping())
    except (RedisError, OSError, ConnectionError) as exc:
        if _is_ci():
            test_case.fail(f"Required Redis integration is unavailable at {url}: {exc}")
        test_case.skipTest(f"Redis integration service is not available at {url}: {exc}")
    _require_or_skip(test_case, connected, f"Redis did not acknowledge PING at {url}.")
    return client


class PostgreSQLIntegrationTests(TestCase):
    def test_django_round_trips_data_through_real_postgresql(self):
        _require_or_skip(
            self,
            connection.vendor == "postgresql",
            f"Real PostgreSQL is required for integration testing; active vendor is {connection.vendor!r}.",
        )

        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_setting('server_version_num')::integer")
            database_name, server_version = cursor.fetchone()

        self.assertTrue(database_name)
        self.assertGreaterEqual(server_version, 120000)

        marker = f"integration-{uuid.uuid4().hex}"
        category = CourseCategory.objects.create(name=marker, slug=marker)
        stored = CourseCategory.objects.get(pk=category.pk)
        self.assertEqual(stored.slug, marker)


class RedisIntegrationTests(SimpleTestCase):
    def test_django_cache_round_trip_uses_real_redis_and_isolated_aliases(self):
        default_url = _redis_url(12)
        public_url = _redis_url(13)
        default_client = _redis_client(self, default_url)
        public_client = _redis_client(self, public_url)
        key = f"integration:{uuid.uuid4().hex}"

        cache_settings = {
            "default": {
                "BACKEND": "amaris_cms.cache.ResilientRedisCache",
                "LOCATION": default_url,
                "KEY_PREFIX": "amaris-integration-default",
                "TIMEOUT": 60,
                "OPTIONS": {"socket_connect_timeout": 2, "socket_timeout": 2},
            },
            "public_content": {
                "BACKEND": "amaris_cms.cache.ResilientRedisCache",
                "LOCATION": public_url,
                "KEY_PREFIX": "amaris-integration-public",
                "TIMEOUT": 60,
                "OPTIONS": {"socket_connect_timeout": 2, "socket_timeout": 2},
            },
        }

        with override_settings(CACHES=cache_settings):
            default_cache = caches["default"]
            public_cache = caches["public_content"]

            self.assertTrue(default_cache.set(key, "default-value", timeout=30))
            self.assertTrue(public_cache.set(key, "public-value", timeout=30))
            self.assertEqual(default_cache.get(key), "default-value")
            self.assertEqual(public_cache.get(key), "public-value")

            default_cache.delete(key)
            public_cache.delete(key)

        # The direct clients are only used to prove that both Redis databases are reachable.
        self.assertTrue(default_client.ping())
        self.assertTrue(public_client.ping())


class CeleryIntegrationTests(SimpleTestCase):
    def test_django_celery_worker_round_trip_uses_real_redis_broker_and_backend(self):
        broker_client = _redis_client(self, settings.CELERY_BROKER_URL)
        result_client = _redis_client(self, settings.CELERY_RESULT_BACKEND)
        self.assertTrue(broker_client.ping())
        self.assertTrue(result_client.ping())

        task_name = f"content.integration_probe.{uuid.uuid4().hex}"

        @celery_app.task(name=task_name, ignore_result=False)
        def integration_probe(payload: dict[str, str]) -> dict[str, str]:
            return payload

        expected = {"status": "ok", "token": uuid.uuid4().hex}
        with start_worker(
            celery_app,
            perform_ping_check=False,
            pool="solo",
            concurrency=1,
            loglevel="WARNING",
        ):
            result = integration_probe.delay(expected)
            self.assertEqual(result.get(timeout=15), expected)
            result.forget()


class StorageIntegrationTests(SimpleTestCase):
    def test_django_storage_abstraction_round_trip_uses_safe_local_adapter(self):
        with tempfile.TemporaryDirectory(prefix="amaris-storage-integration-") as media_root:
            storage_settings = {
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
            }
            with override_settings(MEDIA_ROOT=media_root, STORAGES=storage_settings):
                storage = storages["default"]
                payload = b"amaris-storage-integration"
                saved_name = storage.save(
                    f"integration/{uuid.uuid4().hex}.txt",
                    ContentFile(payload),
                )
                self.assertTrue(storage.exists(saved_name))
                with storage.open(saved_name, "rb") as stored_file:
                    self.assertEqual(stored_file.read(), payload)
                storage.delete(saved_name)
                self.assertFalse(storage.exists(saved_name))


class FrontendApiContractIntegrationTests(TestCase):
    def setUp(self):
        SiteSettings.objects.create()
        NavigationItem.objects.create(
            label="Courses",
            url="/courses",
            location=NavigationItem.Location.BOTH,
            order=10,
        )
        category = CourseCategory.objects.create(name="Integration", slug="integration")
        Course.objects.create(
            category=category,
            title="Integration Calculus",
            slug="integration-calculus",
            short_description="Integration contract course",
            description="Frontend/API integration contract fixture.",
            curriculum="University",
            academic_level="First year",
            price=950,
            status=Course.Status.PUBLISHED,
        )

    def test_frontend_cms_contract_matches_live_django_api_payloads(self):
        frontend_contract = Path(settings.BASE_DIR).parent / "lib" / "cms.ts"
        self.assertTrue(frontend_contract.exists(), "Frontend CMS client lib/cms.ts is missing.")
        source = frontend_contract.read_text(encoding="utf-8")
        self.assertIn('cmsFetch<CmsBootstrap>("/bootstrap/")', source)
        self.assertIn('cmsFetch<Paginated<CmsCourse>>("/courses/?page_size=100")', source)

        bootstrap = self.client.get(reverse("site-bootstrap"))
        self.assertEqual(bootstrap.status_code, 200)
        bootstrap_payload = bootstrap.json()
        self.assertIn("settings", bootstrap_payload)
        self.assertIn("navigation", bootstrap_payload)
        self.assertEqual(bootstrap_payload["settings"]["site_name"], "Amaris Mathematics Academy")
        self.assertEqual(bootstrap_payload["navigation"][0]["url"], "/courses")

        courses = self.client.get(reverse("courses-list"), {"page_size": 100})
        self.assertEqual(courses.status_code, 200)
        course_payload = courses.json()["results"][0]
        for field in (
            "slug",
            "title",
            "curriculum",
            "academic_level",
            "price",
            "short_description",
            "estimated_hours",
            "featured",
            "lesson_count",
        ):
            self.assertIn(field, course_payload)
        self.assertEqual(course_payload["slug"], "integration-calculus")


class ExternalProviderIsolationTests(SimpleTestCase):
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_email_uses_in_memory_adapter_in_tests(self):
        sent = send_mail(
            subject="Integration test",
            message="No external email provider should be contacted.",
            from_email="noreply@example.test",
            recipient_list=["student@example.test"],
        )
        self.assertEqual(sent, 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["student@example.test"])

    def test_external_paid_or_remote_providers_are_not_required_by_real_integration_suite(self):
        # PayFast, WhatsApp, SMS, Zoom, OpenAI, Gemini and YouTube are intentionally
        # outside the real infrastructure integration boundary. Their tests must use
        # sandbox or mock adapters and must never require live credentials here.
        forbidden_live_test_credentials = (
            "PAYFAST_LIVE_SECRET",
            "WHATSAPP_ACCESS_TOKEN",
            "SMS_API_KEY",
            "ZOOM_CLIENT_SECRET",
            "OPENAI_API_KEY",
            "GEMINI_API_KEY",
            "YOUTUBE_CLIENT_SECRET",
        )
        leaked = [name for name in forbidden_live_test_credentials if os.getenv(name)]
        self.assertEqual(
            leaked,
            [],
            f"Live/paid external credentials must not be injected into integration tests: {', '.join(leaked)}",
        )
