from datetime import timedelta

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from content.services.tutor_personnel import deliver_form
from content.tutor_personnel_models import TutorPersonnelForm


@shared_task(ignore_result=True)
def deliver_tutor_personnel_forms():
    now = timezone.now()
    TutorPersonnelForm.objects.filter(delivery_status="sending", sending_at__lt=now - timedelta(hours=1)).update(
        delivery_status="review", error_code="delivery_outcome_unknown"
    )
    ids = list(
        TutorPersonnelForm.objects.filter(delivery_status="queued")
        .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
        .order_by("created_at")
        .values_list("pk", flat=True)[:25]
    )
    sent = 0
    for item_id in ids:
        try:
            sent += deliver_form(item_id)
        except Exception as exc:
            item = TutorPersonnelForm.objects.get(pk=item_id)
            if item.delivery_status == "queued":
                item.attempts += 1
                item.error_code = type(exc).__name__[:40]
                item.next_attempt_at = now + timedelta(minutes=5)
                if item.attempts >= 5:
                    item.delivery_status = "review"
                item.save(update_fields=["attempts", "error_code", "next_attempt_at", "delivery_status", "updated_at"])
    return sent
