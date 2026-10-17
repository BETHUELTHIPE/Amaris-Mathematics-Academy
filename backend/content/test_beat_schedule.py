"""Regression checks for the production Celery Beat routing and scheduling contract."""

from pathlib import Path
from unittest import TestCase

from amaris_cms.beat_schedule import build_beat_schedule
from amaris_cms.celery import app


class CeleryBeatScheduleTests(TestCase):
    def test_every_existing_periodic_job_is_preserved(self):
        schedule = build_beat_schedule()
        self.assertEqual(
            set(schedule),
            {
                "publish-scheduled-content",
                "reconcile-verified-payments",
                "deliver-transactional-email",
                "deliver-live-class-confirmation",
                "deliver-live-class-reminder",
                "expire-live-class-holds",
            },
        )
        self.assertEqual(schedule["deliver-live-class-reminder"]["schedule"], 60.0)
        self.assertEqual(schedule["deliver-live-class-confirmation"]["schedule"], 30.0)
        self.assertEqual(schedule["expire-live-class-holds"]["schedule"], 300.0)

    def test_compose_can_disable_only_duplicate_payment_reconciliation(self):
        schedule = build_beat_schedule(include_reconciliation=False)
        self.assertNotIn("reconcile-verified-payments", schedule)
        self.assertEqual(len(schedule), 5)
        self.assertIn("deliver-live-class-reminder", schedule)
        self.assertIn("deliver-transactional-email", schedule)

    def test_periodic_polling_tasks_have_expiry_and_expected_queue(self):
        schedule = build_beat_schedule()
        for name, entry in schedule.items():
            with self.subTest(job=name):
                self.assertGreater(entry["schedule"], 0)
                self.assertLess(entry["options"]["expires"], entry["schedule"])
                self.assertIn(entry["options"]["queue"], {"default", "critical", "notifications"})
        for name in (
            "deliver-transactional-email",
            "deliver-live-class-confirmation",
            "deliver-live-class-reminder",
        ):
            self.assertEqual(schedule[name]["options"]["queue"], "notifications")
        self.assertEqual(schedule["reconcile-verified-payments"]["options"]["queue"], "critical")
        self.assertEqual(schedule["expire-live-class-holds"]["options"]["queue"], "critical")

    def test_direct_task_dispatch_uses_the_same_worker_queues(self):
        routes = app.conf.task_routes
        for task_name in (
            "content.tasks.deliver_transactional_email",
            "content.tasks.deliver_live_class_confirmation",
            "content.tasks.deliver_live_class_reminder",
        ):
            self.assertEqual(routes[task_name]["queue"], "notifications")
        self.assertEqual(routes["content.tasks.reconcile_payments"]["queue"], "critical")

    def test_compose_disables_only_beat_reconciliation_when_watchdog_is_present(self):
        compose = (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text()
        beat = compose.split("  celery_beat:", 1)[1].split("\n  payment_reconciler:", 1)[0]
        watchdog = compose.split("  payment_reconciler:", 1)[1].split("\n  backup:", 1)[0]
        self.assertIn('CELERY_BEAT_RECONCILIATION_ENABLED: "false"', beat)
        self.assertIn("manage.py reconcile_payments --loop", watchdog)
        self.assertIn("--queues=notifications", compose)
