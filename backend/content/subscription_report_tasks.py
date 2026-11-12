"""Bounded recovery sweep; SMTP uncertainty is held for human review."""

from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from content.services.subscription_reports import deliver_report, eligible_subscriptions, prepare_report
from content.subscription_report_models import SubscriptionReport


@shared_task(ignore_result=True)
def deliver_ended_subscription_reports():
    if not getattr(settings, "SUBSCRIPTION_REPORTS_EMAIL_ENABLED", False):
        return {"sent": 0, "review": 0}
    now = timezone.now()
    SubscriptionReport.objects.filter(status="sending", delivery_started_at__lt=now - timedelta(hours=1)).update(
        status="review", error_code="delivery_outcome_unknown"
    )
    ids = list(
        eligible_subscriptions(now)
        .filter(
            Q(final_report__isnull=True) | Q(final_report__status__in=["pending", "ready"]),
            Q(final_report__next_attempt_at__isnull=True) | Q(final_report__next_attempt_at__lte=now),
        )
        .order_by("ends_at", "pk")
        .values_list("pk", flat=True)[:50]
    )
    sent = review = 0
    for subscription_id in ids:
        report, _ = SubscriptionReport.objects.get_or_create(subscription_id=subscription_id)
        try:
            report = prepare_report(subscription_id)
            if report:
                sent += deliver_report(report.pk)
        except Exception as exc:
            # No recipient, exception message, file content or credentials in error records.
            current = SubscriptionReport.objects.get(subscription_id=subscription_id)
            if current.status in {"pending", "ready"}:
                current.attempts += 1
                current.error_code = type(exc).__name__[:40]
                current.next_attempt_at = now + timedelta(minutes=30)
                if current.attempts >= 5 or isinstance(exc, ValueError):
                    current.status = "review"
                    review += 1
                current.save(update_fields=["status", "attempts", "error_code", "next_attempt_at", "updated_at"])
            # A persisted sending claim is intentionally not made retryable after a DB outage.
    return {"sent": sent, "review": review}
