"""Explicit operator recovery after investigating an ambiguous SMTP outcome."""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from content.subscription_report_models import SubscriptionReport


class Command(BaseCommand):
    help = "Requeue one report only after SMTP logs confirm it was NOT accepted. May otherwise duplicate email."

    def add_arguments(self, parser):
        parser.add_argument("report_id")
        parser.add_argument("--confirm-not-accepted", action="store_true")

    def handle(self, *args, **options):
        if not options["confirm_not_accepted"]:
            raise CommandError("Inspect SMTP/provider logs first, then attest with --confirm-not-accepted.")
        count = (
            SubscriptionReport.objects.filter(
                pk=options["report_id"],
                status="review",
                emailed_at__isnull=True,
            )
            .filter(delivery_started_at__lt=timezone.now() - timedelta(hours=1))
            .update(
                status="ready",
                next_attempt_at=timezone.now(),
                error_code="operator_confirmed_unsent",
            )
        )
        if count != 1:
            raise CommandError("Report is not an unsent reviewed delivery older than one hour.")
        self.stdout.write("One reviewed report requeued. The scheduler will recheck eligibility before sending.")
