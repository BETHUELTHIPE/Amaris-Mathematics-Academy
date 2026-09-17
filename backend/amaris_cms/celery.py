import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")

app = Celery("amaris_cms")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.conf.task_default_queue = "default"
app.conf.task_create_missing_queues = True
app.conf.task_routes = {
    "content.tasks.reconcile_payments": {"queue": "critical"},
    "content.tasks.publish_scheduled_content": {"queue": "default"},
    "content.tasks.deliver_notification_outbox": {"queue": "notifications"},
}
app.autodiscover_tasks()

# Register reliability hooks after Celery has loaded Django settings.
from amaris_cms import celery_signals as _celery_signals  # noqa: E402,F401
