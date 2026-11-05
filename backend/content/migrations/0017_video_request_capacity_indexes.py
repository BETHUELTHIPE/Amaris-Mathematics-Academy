"""Online indexes for large video-request history and paid tutor queues.

PostgreSQL CREATE INDEX CONCURRENTLY must run outside an atomic migration.
Review production lock/time/backup budgets before deploying this migration.
"""

from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("content", "0016_separate_location_fields"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="videorequest",
            index=models.Index(
                fields=("student", "-created_at", "-id"),
                name="video_req_history_v2_idx",
            ),
        ),
        AddIndexConcurrently(
            model_name="videorequest",
            index=models.Index(
                fields=("priority_paid_at", "queue_entered_at"),
                condition=models.Q(status="queued", priority_paid_at__isnull=False),
                name="video_req_priority_v2_idx",
            ),
        ),
        AddIndexConcurrently(
            model_name="videorequest",
            index=models.Index(
                fields=("queue_entered_at",),
                condition=models.Q(status="queued", priority_paid_at__isnull=True),
                name="video_req_fifo_v2_idx",
            ),
        ),
        AddIndexConcurrently(
            model_name="videorequest",
            index=models.Index(
                fields=("queue_entered_at",),
                condition=models.Q(status="queued", confirmation_sent_at__isnull=True),
                name="video_req_confirm_v2_idx",
            ),
        ),
        AddIndexConcurrently(
            model_name="videorequest",
            index=models.Index(
                fields=("provider_reference",),
                name="video_req_provider_v2_idx",
            ),
        ),
    ]
