"""Fail-closed startup preflight for the production Celery email worker and Beat.

This command makes no payments, sends no messages and prints no secret values.
It verifies that the actual runtime can reach the database and Redis; the
notification worker additionally authenticates to the configured SMTP server.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Direct execution puts ops/, rather than backend/, on Python's import path.
# Resolve the application root explicitly for Render and Docker startup.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Amaris notification runtime dependencies.")
    parser.add_argument("--role", choices=("notifications", "beat"), required=True)
    role = parser.parse_args().role

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")
    import django

    django.setup()

    from django.conf import settings
    from django.core.mail import get_connection
    from django.db import connection

    from amaris_cms.celery import app

    _require(bool(os.environ.get("DATABASE_URL")), "DATABASE_URL is not configured.")
    broker = settings.CELERY_BROKER_URL
    _require(
        bool(broker) and broker != "redis://redis:6379/0",
        "The production Celery broker is not configured.",
    )
    if os.getenv("AMARIS_EXTERNAL_WORKER", "").lower() in ("true", "1", "yes"):
        _require(
            broker.startswith("rediss://"),
            "Remote notification containers require a TLS-authenticated rediss:// broker.",
        )
        _require(
            settings.CELERY_RESULT_BACKEND.startswith("rediss://"),
            "Remote notification containers require a TLS-authenticated rediss:// result backend.",
        )

    # Prevent starting against the old booking schema or a wrong database.
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM django_migrations WHERE app = %s AND name = %s)",
            ["content", "0016_separate_location_fields"],
        )
        migrated = cursor.fetchone()[0]
    _require(migrated, "Booking migration 0016 has not been applied to this database.")

    with app.connection_for_write() as broker_connection:
        broker_connection.ensure_connection(max_retries=1)

    for label, task_name in (
        ("deliver-live-class-confirmation", "content.tasks.deliver_live_class_confirmation"),
        ("deliver-live-class-reminder", "content.tasks.deliver_live_class_reminder"),
    ):
        schedule = settings.CELERY_BEAT_SCHEDULE.get(label, {})
        _require(schedule.get("task") == task_name, f"Missing schedule: {label}.")
        _require(
            schedule.get("options", {}).get("queue") == "notifications",
            f"{label} must dispatch to the notifications queue.",
        )

    if role == "notifications":
        _require(
            settings.EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend",
            "The notification worker must use the real SMTP email backend.",
        )
        _require(bool(settings.EMAIL_HOST), "EMAIL_HOST is not configured.")
        _require(bool(settings.EMAIL_HOST_USER), "EMAIL_HOST_USER is not configured.")
        _require(bool(settings.EMAIL_HOST_PASSWORD), "EMAIL_HOST_PASSWORD is not configured.")
        _require(
            bool(settings.DEFAULT_FROM_EMAIL) and "example.invalid" not in settings.DEFAULT_FROM_EMAIL.lower(),
            "DEFAULT_FROM_EMAIL must be a real verified sending address.",
        )
        # SMTP handshake and authentication only; never sends any email.
        mail_connection = get_connection()
        try:
            _require(mail_connection.open(), "The SMTP connection could not be opened.")
        finally:
            mail_connection.close()

    print(f"Amaris {role} dependency preflight passed; no emails were sent.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        # No passwords or connection URLs are printed; unexpected exception
        # details may include infrastructure secrets.
        print(f"Amaris notification preflight failed ({type(exc).__name__}).", file=sys.stderr)
        sys.exit(1)
