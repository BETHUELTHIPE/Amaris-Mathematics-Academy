"""Stdlib-only regression tests: no network, database or SMTP access."""

from __future__ import annotations

import importlib.util
import logging
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

MODULE_PATH = Path(__file__).with_name("colocated_notifications.py")
spec = importlib.util.spec_from_file_location("colocated_notifications_under_test", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


class NotificationSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.supervisor = module.NotificationSupervisor(logging.getLogger("notification-test"))

    def test_default_is_off(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(module.enabled())
        with patch.dict(os.environ, {"AMARIS_COLOCATE_NOTIFICATIONS": "true"}):
            self.assertTrue(module.enabled())

    def test_only_the_notifications_queue_is_consumed(self):
        worker = " ".join(self.supervisor._command("notifications"))
        beat = " ".join(self.supervisor._command("beat"))
        self.assertIn("--queues=notifications", worker)
        self.assertIn("--concurrency=1", worker)
        self.assertIn("--max-memory-per-child=220000", worker)
        self.assertIn(" beat ", " " + beat + " ")
        self.assertNotIn("--queues=critical", worker)

    def test_beat_environment_excludes_critical_and_default_schedules(self):
        beat = self.supervisor._role_environment("beat")
        worker = self.supervisor._role_environment("notifications")
        self.assertEqual(beat["CELERY_NOTIFICATIONS_ONLY_BEAT"], "true")
        self.assertEqual(worker["CELERY_WORKER_MAX_TASKS_PER_CHILD"], "100")
        self.assertEqual(worker["CELERY_BROKER_POOL_LIMIT"], "2")

    @patch.object(module.subprocess, "Popen")
    @patch.object(module.subprocess, "run")
    def test_failed_preflight_does_not_start_celery(self, run, popen):
        run.return_value = Mock(returncode=1)
        self.supervisor._start_role("notifications")
        popen.assert_not_called()
        self.assertNotIn("notifications", self.supervisor.children)

    @patch.object(module.subprocess, "Popen")
    @patch.object(module.subprocess, "run")
    def test_valid_preflight_starts_only_one_worker(self, run, popen):
        run.return_value = Mock(returncode=0)
        process = Mock()
        popen.return_value = process
        self.supervisor._start_role("notifications")
        popen.assert_called_once()
        self.assertIs(self.supervisor.children["notifications"], process)
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.assertEqual(popen.call_args.kwargs["env"]["CELERY_WORKER_MAX_MEMORY_PER_CHILD_KB"], "220000")


    def test_beat_lease_renewal_and_release(self):
        lease = Mock()
        self.supervisor.beat_lease = lease
        self.assertTrue(self.supervisor._renew_beat())
        lease.extend.assert_called_once_with(module.BEAT_LEASE_SECONDS, replace_ttl=True)
        self.supervisor._release_beat()
        lease.release.assert_called_once()
        self.assertIsNone(self.supervisor.beat_lease)

    def test_lost_beat_lease_prevents_unowned_scheduler(self):
        lease = Mock()
        lease.extend.side_effect = RuntimeError("lock no longer owned")
        self.supervisor.beat_lease = lease
        self.assertFalse(self.supervisor._renew_beat())
        self.assertIsNone(self.supervisor.beat_lease)



if __name__ == "__main__":
    unittest.main()
