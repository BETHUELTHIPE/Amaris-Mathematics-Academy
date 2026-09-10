import signal
from threading import Event

from django.core.management.base import BaseCommand

from content.services.reconciliation import reconcile_verified_payments


class Command(BaseCommand):
    help = "Reconcile verified paid payments with enrolments without changing payment status."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Run continuously for the watchdog container.")
        parser.add_argument("--interval", type=int, default=900, help="Seconds between reconciliation runs.")

    def handle(self, *args, **options):
        stop = Event()

        def request_shutdown(_signum, _frame):
            stop.set()

        signal.signal(signal.SIGTERM, request_shutdown)
        signal.signal(signal.SIGINT, request_shutdown)

        while not stop.is_set():
            run = reconcile_verified_payments()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Reconciliation {run.id}: scanned={run.payments_scanned}, "
                    f"repaired={run.enrollments_repaired}, unresolved={run.unresolved_count}"
                )
            )
            if not options["loop"]:
                break
            stop.wait(max(options["interval"], 60))
