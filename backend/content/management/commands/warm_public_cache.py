from __future__ import annotations

import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test import Client


class Command(BaseCommand):
    help = "Warm the bounded public-content cache before expected traffic peaks."

    def handle(self, *args, **options):
        host = os.getenv("CACHE_WARM_HOST", "").strip() or next(
            (value for value in settings.ALLOWED_HOSTS if value not in {"*", "localhost", "127.0.0.1"}),
            "localhost",
        )
        paths = (
            "/api/v1/bootstrap/",
            "/api/v1/courses/",
            "/api/v1/pricing-plans/",
            "/api/v1/faqs/",
            "/api/v1/announcements/",
        )
        client = Client(HTTP_HOST=host)
        failures: list[str] = []
        for path in paths:
            response = client.get(path, secure=True)
            if response.status_code != 200:
                failures.append(f"{path} -> HTTP {response.status_code}")
            else:
                self.stdout.write(self.style.SUCCESS(f"Warmed {path}"))
        if failures:
            raise CommandError("Cache warm failed: " + "; ".join(failures))
