import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")

app = Celery("amaris_cms")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.conf.task_default_queue = "default"
app.conf.task_create_missing_queues = True
# Keep task routing aligned with the actual registered task names.
# Beat and direct .delay()/apply_async() submissions must reach the same workers.
app.conf.task_routes = {
    "content.tasks.reconcile_payments": {"queue": "critical"},
    "content.tasks.expire_live_class_holds": {"queue": "critical"},
    "content.tasks.publish_scheduled_content": {"queue": "default"},
    "content.tasks.deliver_transactional_email": {"queue": "notifications"},
    "content.tasks.deliver_live_class_confirmation": {"queue": "notifications"},
    "content.tasks.deliver_live_class_reminder": {"queue": "notifications"},
}
app.autodiscover_tasks()

# Register reliability hooks after Celery has loaded Django settings.
from amaris_cms import celery_signals as _celery_signals  # noqa: E402,F401
