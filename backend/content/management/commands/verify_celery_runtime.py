"""Verify actual Celery broker -> worker -> result-backend execution on staging.

Run inside the deployed backend's environment with the same broker and result
backend as the workers. This command does not send notifications or charge users.
"""

import secrets

from django.core.management.base import BaseCommand, CommandError

from amaris_cms.celery import app


class Command(BaseCommand):
    help = "Safely confirm all Celery worker queues execute tasks through Redis."

    def add_arguments(self, parser):
        parser.add_argument("--timeout", type=int, default=20)

    def handle(self, *args, **options):
        timeout = options["timeout"]
        if not 1 <= timeout <= 120:
            raise CommandError("Timeout must be between 1 and 120 seconds.")
        if app.conf.task_always_eager:
            raise CommandError("Eager Celery mode cannot verify deployed workers.")
        if not app.conf.result_backend:
            raise CommandError("A Celery result backend is required for a real execution check.")

        for queue in ("critical", "default", "notifications"):
            nonce = secrets.token_hex(16)
            try:
                result = app.send_task(
                    "content.tasks.runtime_worker_probe",
                    args=(nonce,),
                    queue=queue,
                    expires=max(30, timeout * 2),
                    ignore_result=False,
                )
                payload = result.get(timeout=timeout, propagate=True)
                if payload != {"nonce": nonce, "queue": queue}:
                    raise CommandError(
                        f"{queue}: unexpected worker response or wrong queue routing."
                    )
                result.forget()
            except CommandError:
                raise
            except Exception as exc:
                raise CommandError(
                    f"{queue}: real worker execution failed; inspect private Celery/Redis logs."
                ) from exc
            self.stdout.write(self.style.SUCCESS(f"{queue}: broker -> worker -> result backend PASS"))
