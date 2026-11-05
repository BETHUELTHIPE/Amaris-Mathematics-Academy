import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")

from django.conf import settings  # noqa: E402

from amaris_cms.telemetry import initialize_tracing  # noqa: E402

_ = settings.INSTALLED_APPS
initialize_tracing("web")
application = get_wsgi_application()
