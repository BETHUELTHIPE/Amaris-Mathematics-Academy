"""Superuser-only Celery monitoring and secret-safe snapshot regression tests."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from amaris_cms.celery_monitor import get_task_snapshot
from amaris_cms.monitoring_admin import AmarisAdminSite


class CelerySnapshotTests(SimpleTestCase):
    @patch("amaris_cms.celery_monitor.celery_app.control.inspect")
    @patch("amaris_cms.celery_monitor.Redis.from_url")
    def test_live_worker_counts_queue_counts_and_no_private_payload(self, connect, inspect):
        client = connect.return_value
        client.ping.return_value = True
        client.llen.side_effect = [4, 2, 0, 1]
        inspector = inspect.return_value
        inspector.active.return_value = {
            "worker-private-host": [
                {"id": "student-secret", "args": ["private-student-email"], "name": "content.tasks.notify"}
            ]
        }
        inspector.reserved.return_value = {"worker-private-host": [{}, {}]}
        inspector.scheduled.return_value = {"worker-private-host": []}

        result = get_task_snapshot()

        self.assertEqual(result["state"], "healthy")
        self.assertTrue(result["broker_online"])
        self.assertEqual(result["worker_count"], 1)
        self.assertEqual(result["queue_depths"], {"default": 4, "critical": 2, "notifications": 0})
        self.assertEqual(result["task_counts"], {"active": 1, "reserved": 2, "scheduled": 0})
        self.assertEqual(result["failed_task_records"], 1)
        self.assertFalse(result["beat_liveness_verified"])
        self.assertNotIn("private-student-email", repr(result))
        self.assertNotIn("student-secret", repr(result))
        self.assertNotIn("worker-private-host", repr(result))
        client.close.assert_called_once()

    @patch("amaris_cms.celery_monitor.celery_app.control.inspect")
    @patch("amaris_cms.celery_monitor.Redis.from_url")
    def test_redis_failure_does_not_claim_healthy_workers(self, connect, inspect):
        connect.side_effect = OSError("redis://user:secret@example.invalid")
        result = get_task_snapshot()
        self.assertEqual(result["state"], "unavailable")
        self.assertFalse(result["broker_online"])
        self.assertNotIn("secret", repr(result))
        inspect.assert_not_called()

    @patch("amaris_cms.celery_monitor.celery_app.control.inspect")
    @patch("amaris_cms.celery_monitor.Redis.from_url")
    def test_missing_workers_are_degraded_even_with_healthy_redis(self, connect, inspect):
        client = connect.return_value
        client.ping.return_value = True
        client.llen.return_value = 0
        inspect.return_value.active.return_value = None
        inspect.return_value.reserved.return_value = None
        inspect.return_value.scheduled.return_value = None

        result = get_task_snapshot()

        self.assertEqual(result["state"], "degraded")
        self.assertEqual(result["worker_count"], 0)
        self.assertTrue(result["worker_data_partial"])

    @patch("amaris_cms.celery_monitor.celery_app.control.inspect")
    @patch("amaris_cms.celery_monitor.Redis.from_url")
    def test_worker_inspection_exception_is_sanitized(self, connect, inspect):
        client = connect.return_value
        client.ping.return_value = True
        client.llen.return_value = 0
        inspect.side_effect = RuntimeError("Sensitive worker token")
        result = get_task_snapshot()
        self.assertEqual(result["state"], "degraded")
        self.assertNotIn("Sensitive", repr(result))


class TaskOperationsAdminTests(SimpleTestCase):
    def setUp(self):
        self.site = AmarisAdminSite()
        self.factory = RequestFactory()
        self.superuser = SimpleNamespace(
            is_authenticated=True, is_active=True, is_staff=True, is_superuser=True
        )
        self.staff = SimpleNamespace(
            is_authenticated=True, is_active=True, is_staff=True, is_superuser=False
        )

    @patch("amaris_cms.monitoring_admin.get_task_snapshot")
    def test_superuser_can_view_dashboard_and_status(self, snapshot):
        snapshot.return_value = {
            "state": "degraded", "broker_online": True, "worker_count": 0,
            "queue_depths": {}, "task_counts": {"active": 0, "reserved": 0, "scheduled": 0},
        }
        self.assertEqual(reverse("admin:amaris_task_operations_home"), "/admin/task-operations/")
        self.assertEqual(reverse("admin:amaris_task_operations_status"), "/admin/task-operations/status/")
        request = self.factory.get("/admin/task-operations/")
        request.user = self.superuser
        with patch("amaris_cms.monitoring_admin.is_configured", return_value=False):
            page = self.site.task_operations_home(request)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context_data["snapshot"]["state"], "degraded")
        self.assertEqual(page["Cache-Control"], "private, no-store")

        request = self.factory.get("/admin/task-operations/status/")
        request.user = self.superuser
        response = self.site.task_operations_status(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertIn(b'"state": "degraded"', response.content)

    @patch("amaris_cms.monitoring_admin.get_task_snapshot")
    def test_staff_and_unauthenticated_users_are_denied(self, snapshot):
        request = self.factory.get("/admin/task-operations/status/")
        request.user = self.staff
        with self.assertRaises(PermissionDenied):
            self.site.task_operations_status(request)
        request.user = SimpleNamespace(
            is_authenticated=False, is_active=False, is_staff=False, is_superuser=False
        )
        with self.assertRaises(PermissionDenied):
            self.site.task_operations_home(request)
        snapshot.assert_not_called()

    @patch("amaris_cms.monitoring_admin.get_task_snapshot")
    def test_writes_and_task_actions_are_blocked(self, snapshot):
        request = self.factory.post("/admin/task-operations/status/", data={"revoke": "123"})
        request.user = self.superuser
        self.assertEqual(self.site.task_operations_status(request).status_code, 405)
        snapshot.assert_not_called()

    @patch("amaris_cms.monitoring_admin.get_task_snapshot")
    def test_task_status_does_not_echo_browser_supplied_data(self, snapshot):
        snapshot.return_value = {"state": "unavailable"}
        request = self.factory.get("/admin/task-operations/status/?task_id=private")
        request.user = self.superuser
        response = self.site.task_operations_status(request)
        self.assertNotIn(b"private", response.content)
        self.assertNotIn(b"task_id", response.content)
