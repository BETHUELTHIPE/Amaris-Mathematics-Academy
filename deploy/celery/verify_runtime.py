"""Check the checked-out Django release without touching data or sending work."""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")

import django

django.setup()

from amaris_cms.celery import app

app.loader.import_default_modules()
assert not app.conf.task_always_eager, "Tasks must execute on workers"
assert app.conf.timezone == "Africa/Johannesburg", "Use South African time for schedules"
assert app.conf.task_acks_late and app.conf.task_reject_on_worker_lost
assert app.conf.worker_prefetch_multiplier == 1
assert app.conf.broker_connection_retry_on_startup
assert app.conf.accept_content == ["json"]

expected_notifications = {
    "content.tasks.deliver_transactional_email",
    "content.tasks.deliver_live_class_confirmation",
    "content.tasks.deliver_live_class_reminder",
    "content.tasks.deliver_video_request_notifications",
    "content.tasks.deliver_tutor_application_acknowledgements",
    "content.tasks.archive_missing_invoice_pdfs",
    "content.tutor_finance_tasks.email_tutor_payout_receipt",
}
scheduled = set()
for entry in app.conf.beat_schedule.values():
    task = entry["task"]
    assert task in app.tasks, f"Scheduled task is unregistered: {task}"
    route = app.amqp.router.route(entry.get("options", {}), task, args=(), kwargs={})
    queue = route["queue"].name
    assert queue in {"critical", "default", "notifications"}
    if task in expected_notifications:
        assert queue == "notifications", f"Email/archive scheduled on the wrong queue: {task}"
    scheduled.add(task)
assert expected_notifications <= scheduled, "Required notification schedules are missing"
assert "content.tasks.reconcile_payments" in scheduled
assert "content.tasks.expire_live_class_holds" in scheduled
print(f"DJANGO_CELERY_SCHEDULE_AND_ROUTING=PASS ({len(scheduled)} registered scheduled tasks)")
print("SMTP dispatch, live workers and deployed acceptance: NOT TESTED by this static runtime check")
