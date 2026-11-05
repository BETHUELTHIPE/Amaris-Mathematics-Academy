"""Read-only acceptance of the Airflow connection used by Django Admin."""

from django.core.management.base import BaseCommand, CommandError

from amaris_cms.airflow_client import AirflowUnavailable, check_runtime


class Command(BaseCommand):
    help = "Verify private Airflow TLS/API, component health and a fresh unpaused successful health DAG."

    def add_arguments(self, parser):
        parser.add_argument("--dag-id", default="amaris_service_health")
        parser.add_argument("--max-run-age-minutes", type=int, default=30)

    def handle(self, *args, **options):
        try:
            check_runtime(options["dag_id"], max_run_age_minutes=options["max_run_age_minutes"])
        except (AirflowUnavailable, ValueError):
            raise CommandError(
                "Airflow readiness NOT VERIFIED. Check secure configuration, component health "
                "and a recent successful unpaused health DAG."
            ) from None
        self.stdout.write(self.style.SUCCESS("PASS: Airflow API, components and recent scheduled health run verified."))
