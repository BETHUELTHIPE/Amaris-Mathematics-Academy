from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import FeedbackFollowUp


def create_followup_for_form(form):
    """Create exactly one administrator follow-up for an unhappy student."""
    if form.overall_rating > 2 and (form.tutor_rating is None or form.tutor_rating > 2):
        return None
    followup, created = FeedbackFollowUp.objects.get_or_create(
        feedback=form,
        defaults={"due_at": form.created_at + timedelta(days=2)},
    )
    if created:
        from .tasks import notify_new_followup

        transaction.on_commit(lambda: notify_new_followup.delay(followup.pk))
    return followup
