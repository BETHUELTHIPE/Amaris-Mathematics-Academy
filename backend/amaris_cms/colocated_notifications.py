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
_SUPERVISOR = None


def enabled() -> bool:
    return os.getenv("AMARIS_COLOCATE_NOTIFICATIONS", "").lower() in {"1", "true", "yes"}


class NotificationSupervisor:
    def __init__(self, log):
        self.log = log
        self.stop_event = threading.Event()
        self.children: dict[str, subprocess.Popen] = {}
        self.next_attempt: dict[str, float] = {}
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

    def _run(self):
        while not self.stop_event.is_set():
            now = time.monotonic()
            for role in ROLES:
                child = self.children.get(role)
                if child is not None and child.poll() is not None:
                    self.children.pop(role, None)
                    self.next_attempt[role] = now + RESTART_DELAY_SECONDS
                    self.log.warning("Amaris %s exited; supervisor will restart it", role)
                if role not in self.children and now >= self.next_attempt.get(role, 0):
                    self._start_role(role)
            self.stop_event.wait(10)

    def stop(self):
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=2)
        for role, child in list(self.children.items()):
            if child.poll() is None:
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                    child.wait(timeout=12)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            self.children.pop(role, None)
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
