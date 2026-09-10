import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")

app = Celery("amaris_cms")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
