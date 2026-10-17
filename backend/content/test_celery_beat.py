"""Regression contracts for the single, durable Amaris Celery Beat scheduler."""

from django.conf import settings
from django.test import SimpleTestCase

from amaris_cms.settings import env_bool


class CeleryBeatConfigurationTests(SimpleTestCase):
    def test_publishing_runs_every_minute_and_old_jobs_expire(self):
        entry = settings.CELERY_BEAT_SCHEDULE["publish-scheduled-content"]
        self.assertEqual(entry["task"], "content.tasks.publish_scheduled_content")
        self.assertEqual(entry["schedule"], 60.0)
        self.assertEqual(entry["options"]["expires"], 60)

    def test_payment_job_is_enabled_only_for_beat_owned_reconciliation(self):
        enabled = env_bool("CELERY_BEAT_PAYMENT_RECONCILIATION_ENABLED", True)
        schedule = settings.CELERY_BEAT_SCHEDULE
        self.assertEqual("reconcile-verified-payments" in schedule, enabled)
        if enabled:
            payment = schedule["reconcile-verified-payments"]
            self.assertEqual(payment["task"], "content.tasks.reconcile_payments")
            self.assertEqual(payment["schedule"], 300.0)
            self.assertEqual(payment["options"]["expires"], 300)

    def test_schedule_is_synced_frequently_without_tight_polling(self):
        self.assertEqual(settings.CELERY_BEAT_SYNC_EVERY, 1)
        self.assertEqual(settings.CELERY_BEAT_MAX_LOOP_INTERVAL, 30)

    def test_compose_uses_durable_schedule_and_avoids_duplicate_payment_ticks(self):
        compose = (settings.BASE_DIR / "docker-compose.yml").read_text(encoding="utf-8")
        beat = compose.split("\n  celery_beat:\n", 1)[1].split(
            "\n  payment_reconciler:\n", 1
        )[0]
        self.assertIn("--schedule=/app/beat/celerybeat-schedule", beat)
        self.assertIn("celery_beat_state:/app/beat", beat)
        self.assertIn('CELERY_BEAT_PAYMENT_RECONCILIATION_ENABLED: "false"', beat)
        self.assertIn("\n  celery_beat_state:\n", compose)

    def test_non_root_image_contains_writable_beat_directory(self):
        dockerfile = (settings.BASE_DIR / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("/app/staticfiles /app/media /app/beat", dockerfile)
        self.assertIn("chown -R amaris:amaris /app", dockerfile)
        self.assertIn("USER amaris", dockerfile)
