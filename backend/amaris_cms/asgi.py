"""ASGI entrypoint for the Amaris Django backend."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")

application = get_asgi_application()
