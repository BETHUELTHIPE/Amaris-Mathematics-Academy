from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from content.tutor_personnel_models import TutorPersonnelForm


class Command(BaseCommand):
    help = "Requeue a reviewed personnel email only after independently confirming the provider did not accept it."

    def add_arguments(self, parser):
        parser.add_argument("form_id")
        parser.add_argument("--confirm-not-accepted", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        if not options["confirm_not_accepted"]:
            raise CommandError("Confirm the provider did not accept this Message-ID before retrying.")
        try:
            item = TutorPersonnelForm.objects.select_for_update().get(pk=options["form_id"])
        except (TutorPersonnelForm.DoesNotExist, ValueError, ValidationError) as exc:
            raise CommandError("Form not found.") from exc
        if item.delivery_status != "review" or item.sent_at:
            raise CommandError("Only unsent delivery-review forms can be requeued.")
        if item.sending_at and item.sending_at > timezone.now() - timedelta(hours=1):
            raise CommandError("Allow one hour for a possibly active sender before retrying.")
        item.delivery_status, item.error_code, item.next_attempt_at = "queued", "reviewed_not_accepted", None
        item.save(update_fields=["delivery_status", "error_code", "next_attempt_at", "updated_at"])
        self.stdout.write("Confirmed non-acceptance recorded; form queued for one further delivery attempt.")
