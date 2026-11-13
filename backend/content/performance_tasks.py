from datetime import timedelta

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from content.performance_models import PerformanceDigest
from content.services.performance_reports import deliver_report, generate_due_report


@shared_task(ignore_result=True)
def process_performance_reports():
    # The persisted 14-day anchor, rather than a 14-day worker uptime interval,
    # determines eligibility. Restarting Beat cannot reset or duplicate a period.
    from django.conf import settings

    if not settings.ADMIN_PERFORMANCE_REPORTS_ENABLED:
        return 0
    generate_due_report()
    now = timezone.now()
    PerformanceDigest.objects.filter(delivery_status="sending", sending_at__lt=now - timedelta(hours=1)).update(
        delivery_status="review", error_code="delivery_outcome_unknown"
    )
    ids = list(
        PerformanceDigest.objects.filter(delivery_status="queued")
        .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
        .order_by("created_at")
        .values_list("pk", flat=True)[:5]
    )
    sent = 0
    for item_id in ids:
        try:
            sent += deliver_report(item_id)
        except Exception as exc:
            item = PerformanceDigest.objects.get(pk=item_id)
            if item.delivery_status == "queued":
                item.attempts += 1
                item.error_code = type(exc).__name__[:40]
                item.next_attempt_at = now + timedelta(minutes=10)
                if item.attempts >= 5:
                    item.delivery_status = "review"
                item.save(update_fields=["attempts", "error_code", "next_attempt_at", "delivery_status", "updated_at"])
    return sent
