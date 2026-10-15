from django.core.management.base import BaseCommand

from content.services.tutor_applications import deliver_application_acknowledgement


class Command(BaseCommand):
    help = "Deliver pending tutor application acknowledgements (also recovered by Celery beat)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        delivered = 0
        for _ in range(max(1, min(options["limit"], 1000))):
            count = deliver_application_acknowledgement()
            delivered += count
            if not count:
                break
        self.stdout.write(f"Delivered {delivered} tutor acknowledgement(s).")
