"""Optional Celery sidecars supervised by the *single* paid Render web instance.

No additional Render services and no external Redis access are required.
This feature defaults off; enable only after the booking migration, live SMTP
credentials, queue access and real production backup have been verified.

Gunicorn owns this supervisor in its master process, not in ASGI workers.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROLES = ("notifications", "beat")
RESTART_DELAY_SECONDS = 45
BEAT_LEASE_SECONDS = 45
BEAT_LOCK_KEY = "amaris:celery:notification-beat:singleton"
_SUPERVISOR = None


def enabled() -> bool:
    return os.getenv("AMARIS_COLOCATE_NOTIFICATIONS", "").lower() in {"1", "true", "yes"}


class NotificationSupervisor:
    def __init__(self, log):
        self.log = log
        self.stop_event = threading.Event()
        self.children: dict[str, subprocess.Popen] = {}
        self.next_attempt: dict[str, float] = {}
        self.beat_lease = None
        self.thread = threading.Thread(target=self._run, name="amaris-celery-supervisor", daemon=True)

    def start(self):
        self.thread.start()

    def _role_environment(self, role: str) -> dict[str, str]:
        env = os.environ.copy()
        env["CELERY_BROKER_POOL_LIMIT"] = "2"
        if role == "beat":
            # Never schedule unconsumed critical/default queues in the shared web.
            env["CELERY_NOTIFICATIONS_ONLY_BEAT"] = "true"
        else:
            env["CELERY_WORKER_MAX_TASKS_PER_CHILD"] = "100"
            env["CELERY_WORKER_MAX_MEMORY_PER_CHILD_KB"] = "220000"
        return env

    def _command(self, role: str) -> list[str]:
        if role == "beat":
            return [
                sys.executable,
                "-m",
                "celery",
                "-A",
                "amaris_cms",
                "beat",
                "--loglevel=INFO",
                "--pidfile=/tmp/amaris-notify-beat.pid",
                "--schedule=/tmp/amaris-notify-beat-schedule",
            ]
        return [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "amaris_cms",
            "worker",
            "--loglevel=INFO",
            "--queues=notifications",
            "--pool=prefork",
            "--concurrency=1",
            "--prefetch-multiplier=1",
            "--max-tasks-per-child=100",
            "--max-memory-per-child=220000",
            "--hostname=amaris-notifications@%h",
        ]

    def _start_role(self, role: str):
        env = self._role_environment(role)
        self.next_attempt[role] = time.monotonic() + RESTART_DELAY_SECONDS
        try:
            # Do not print credentials or raw exception text.
            check = subprocess.run(
                [sys.executable, "ops/check_notifications.py", "--role", role],
                cwd=BACKEND_DIR,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=25,
                check=False,
            )
            if check.returncode != 0:
                self.log.warning("Amaris %s preflight failed; retrying later (web remains available)", role)
                return
            if self.stop_event.is_set():
                return
            self.children[role] = subprocess.Popen(
                self._command(role),
                cwd=BACKEND_DIR,
                env=env,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
            self.log.info("Amaris %s started in existing web service", role)
        except (OSError, subprocess.TimeoutExpired):
            self.log.warning("Amaris %s startup failed; retrying later", role)

    def _claim_beat(self) -> bool:
        # Prevent overlapping Beat processes during Render rolling deploys.
        # Lease lives in the existing private production Redis broker.
        try:
            from redis import Redis

            redis = Redis.from_url(
                os.environ["CELERY_BROKER_URL"],
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            lease = redis.lock(
                BEAT_LOCK_KEY, timeout=BEAT_LEASE_SECONDS, blocking=False, thread_local=False
            )
            if lease.acquire(blocking=False):
                self.beat_lease = lease
                return True
        except (KeyError, OSError, ValueError):
            self.log.warning("Amaris Beat lease unavailable; web remains available")
        except Exception:
            self.log.warning("Amaris Beat lease check failed; web remains available")
        return False

    def _release_beat(self):
        lease, self.beat_lease = self.beat_lease, None
        if lease is not None:
            try:
                lease.release()
            except Exception:
                pass

    def _renew_beat(self) -> bool:
        if self.beat_lease is None:
            return False
        try:
            self.beat_lease.extend(BEAT_LEASE_SECONDS, replace_ttl=True)
            return True
        except Exception:
            self.log.warning("Amaris Beat lease lost; stopping duplicate scheduler")
            self._release_beat()
            return False

    def _run(self):
        while not self.stop_event.is_set():
            now = time.monotonic()
            for role in ROLES:
                child = self.children.get(role)
                if child is not None and child.poll() is not None:
                    self.children.pop(role, None)
                    self.next_attempt[role] = now + RESTART_DELAY_SECONDS
                    self.log.warning("Amaris %s exited; supervisor will restart it", role)
                if role == "beat":
                    # Do not enqueue messages while SMTP/worker preflight is failing.
                    worker = self.children.get("notifications")
                    if worker is None or worker.poll() is not None:
                        if child is not None and child.poll() is None:
                            self._terminate_child(child)
                            self.children.pop(role, None)
                        self._release_beat()
                        continue
                    if child is not None and child.poll() is None and not self._renew_beat():
                        self._terminate_child(child)
                        self.children.pop(role, None)
                        continue
                    if child is None and now >= self.next_attempt.get(role, 0):
                        if not self._claim_beat():
                            continue
                        self._start_role(role)
                        if role not in self.children:
                            self._release_beat()
                        continue
                if role not in self.children and now >= self.next_attempt.get(role, 0):
                    self._start_role(role)
            self.stop_event.wait(10)

    @staticmethod
    def _terminate_child(child):
        if child.poll() is not None:
            return
        try:
            os.killpg(child.pid, signal.SIGTERM)
            child.wait(timeout=12)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def stop(self):
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=2)
        # Stop Beat first so new jobs are not published during worker shutdown.
        for role in reversed(ROLES):
            child = self.children.pop(role, None)
            if child is not None:
                self._terminate_child(child)
        self._release_beat()
        self.log.info("Amaris colocated notification processes stopped")


def start_notifications(log):
    global _SUPERVISOR
    if not enabled() or _SUPERVISOR is not None:
        return
    _SUPERVISOR = NotificationSupervisor(log)
    _SUPERVISOR.start()


def stop_notifications(log):
    global _SUPERVISOR
    if _SUPERVISOR is not None:
        _SUPERVISOR.stop()
        _SUPERVISOR = None
