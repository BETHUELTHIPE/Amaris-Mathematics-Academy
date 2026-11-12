from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from content.tutor_video_models import TutorVideoUpload


class Command(BaseCommand):
    help = "Requeue a reviewed upload alert only after SMTP logs confirm it was not accepted."

    def add_arguments(self, parser):
        parser.add_argument("activity_id")
        parser.add_argument("--confirm-not-accepted", action="store_true")

    def handle(self, *args, **options):
        if not options["confirm_not_accepted"]:
            raise CommandError(
                "Inspect provider logs and attest with --confirm-not-accepted; "
                "otherwise a resend may duplicate email."
            )
        count = TutorVideoUpload.objects.filter(
            pk=options["activity_id"],
            delivery_status="review",
            sent_at__isnull=True,
            sending_at__lt=timezone.now() - timedelta(hours=1),
        ).update(delivery_status="queued", next_attempt_at=timezone.now(), error_code="operator_confirmed_unsent")
        if count != 1:
            raise CommandError("This is not an unsent reviewed delivery older than one hour.")
        self.stdout.write("One reviewed Admin alert requeued.")
