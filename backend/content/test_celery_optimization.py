"""Contract tests for Celery delivery throughput and existing worker queues.

These tests use mocks only: no Redis publish, SMTP, payment, Zoom, or OpenAI calls.
The existing payment/live-class integration tests exercise the real database path.
"""

from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from amaris_cms.celery import app
from content.tasks import (
    deliver_live_class_confirmation,
    deliver_live_class_reminder,
    deliver_transactional_email,
)


class CeleryRoutingTests(SimpleTestCase):
    def test_all_known_tasks_have_a_worker_queue(self):
        expected = {
            "content.tasks.reconcile_payments": "critical",
            "content.tasks.expire_live_class_holds": "critical",
            "content.tasks.publish_scheduled_content": "default",
            "content.tasks.deliver_transactional_email": "notifications",
            "content.tasks.deliver_live_class_confirmation": "notifications",
            "content.tasks.deliver_live_class_reminder": "notifications",
        }
        for task_name, queue_name in expected.items():
            with self.subTest(task_name=task_name):
                route = app.amqp.router.route({}, task_name)
                self.assertEqual(route["queue"].name, queue_name)

    def test_beat_notification_routes_match_direct_submissions(self):
        for schedule_name in (
            "deliver-transactional-email",
            "deliver-live-class-confirmation",
            "deliver-live-class-reminder",
        ):
            with self.subTest(schedule_name=schedule_name):
                self.assertEqual(
                    settings.CELERY_BEAT_SCHEDULE[schedule_name]["options"]["queue"],
                    "notifications",
                )

    def test_notifications_batch_setting_is_bounded(self):
        self.assertGreaterEqual(settings.CELERY_NOTIFICATION_BATCH_SIZE, 1)
        self.assertLessEqual(settings.CELERY_NOTIFICATION_BATCH_SIZE, 25)


class CeleryNotificationBatchTests(SimpleTestCase):
    @override_settings(CELERY_NOTIFICATION_BATCH_SIZE=3)
    @patch("content.tasks._deliver_one_transactional_email", side_effect=[1, 1, 0])
    def test_payment_email_drain_stops_when_queue_empty(self, send_one):
        self.assertEqual(deliver_transactional_email.run(), 2)
        self.assertEqual(send_one.call_count, 3)

    @override_settings(CELERY_NOTIFICATION_BATCH_SIZE=3)
    @patch("content.tasks._deliver_one_live_class_confirmation", return_value=1)
    def test_live_class_confirmations_are_batched(self, send_one):
        self.assertEqual(deliver_live_class_confirmation.run(), 3)
        self.assertEqual(send_one.call_count, 3)

    @override_settings(CELERY_NOTIFICATION_BATCH_SIZE=3)
    @patch("content.tasks._deliver_one_live_class_reminder", side_effect=[1, 0])
    def test_reminders_stop_when_no_more_bookings(self, send_one):
        self.assertEqual(deliver_live_class_reminder.run(), 1)
        self.assertEqual(send_one.call_count, 2)

    @override_settings(CELERY_NOTIFICATION_BATCH_SIZE=100)
    @patch("content.tasks._deliver_one_transactional_email", return_value=1)
    def test_batch_is_hard_capped_at_twenty_five(self, send_one):
        self.assertEqual(deliver_transactional_email.run(), 25)
        self.assertEqual(send_one.call_count, 25)

    @override_settings(CELERY_NOTIFICATION_BATCH_SIZE=0)
    @patch("content.tasks._deliver_one_transactional_email", return_value=1)
    def test_batch_runs_at_least_once(self, send_one):
        self.assertEqual(deliver_transactional_email.run(), 1)
        send_one.assert_called_once()
