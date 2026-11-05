"""ASGI entrypoint for the Amaris Django backend."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")

# Load server secret files, then instrument before Django builds middleware.
from django.conf import settings  # noqa: E402

from amaris_cms.telemetry import initialize_tracing  # noqa: E402

_ = settings.INSTALLED_APPS
initialize_tracing("web")
application = get_asgi_application()
