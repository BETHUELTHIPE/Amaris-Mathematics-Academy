from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from content.performance_models import PerformanceDigest


class Command(BaseCommand):
    help = "Requeue a reviewed Admin performance email only after confirming provider non-acceptance."

    def add_arguments(self, parser):
        parser.add_argument("report_id")
        parser.add_argument("--confirm-not-accepted", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        if not options["confirm_not_accepted"]:
            raise CommandError("Independently confirm this Message-ID was not accepted before requeueing.")
        try:
            item = PerformanceDigest.objects.select_for_update().get(pk=options["report_id"])
        except (PerformanceDigest.DoesNotExist, ValueError, ValidationError) as exc:
            raise CommandError("Report not found.") from exc
        if item.delivery_status != "review" or item.sent_at:
            raise CommandError("Only unsent reports held for delivery review may be requeued.")
        if item.sending_at and item.sending_at > timezone.now() - timedelta(hours=1):
            raise CommandError("Allow an hour for a possibly active sender before retrying.")
        item.delivery_status, item.error_code, item.next_attempt_at = "queued", "reviewed_not_accepted", None
        item.save(update_fields=["delivery_status", "error_code", "next_attempt_at", "updated_at"])
        self.stdout.write("Provider non-acceptance confirmed; report queued for another delivery attempt.")
