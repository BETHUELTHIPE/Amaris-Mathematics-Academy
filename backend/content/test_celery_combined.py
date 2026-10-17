"""Combined regression checks for Celery Beat, routing and notification batching.

All operations here are configuration assertions: no broker publishes, SMTP sends,
PayFast charges, Zoom meetings or external API requests occur.
"""

from django.test import SimpleTestCase

from amaris_cms.beat_schedule import build_beat_schedule
from amaris_cms.celery import app


class CombinedCeleryReleaseTests(SimpleTestCase):
    def test_beat_queue_and_direct_dispatch_agree_for_every_task(self):
        for name, job in build_beat_schedule().items():
            with self.subTest(job=name):
                routed = app.amqp.router.route({}, job["task"])
                self.assertEqual(routed["queue"].name, job["options"]["queue"])

    def test_compose_watchdog_and_beat_do_not_schedule_duplicate_payments(self):
        standalone = build_beat_schedule(include_reconciliation=True)
        compose = build_beat_schedule(include_reconciliation=False)
        self.assertIn("reconcile-verified-payments", standalone)
        self.assertNotIn("reconcile-verified-payments", compose)
        self.assertEqual(
            set(standalone) - set(compose), {"reconcile-verified-payments"}
        )

    def test_essential_student_notification_jobs_survive_watchdog_override(self):
        jobs = build_beat_schedule(include_reconciliation=False)
        for name in (
            "deliver-transactional-email",
            "deliver-live-class-confirmation",
            "deliver-live-class-reminder",
        ):
            with self.subTest(job=name):
                self.assertIn(name, jobs)
                self.assertEqual(jobs[name]["options"]["queue"], "notifications")
                self.assertLess(jobs[name]["options"]["expires"], jobs[name]["schedule"])

    def test_payment_and_booking_expiry_share_critical_worker(self):
        jobs = build_beat_schedule()
        for name in ("reconcile-verified-payments", "expire-live-class-holds"):
            with self.subTest(job=name):
                self.assertEqual(jobs[name]["options"]["queue"], "critical")
