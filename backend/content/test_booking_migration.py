import uuid

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TransactionTestCase
from django.utils import timezone

from amaris_cms.celery import app


class BookingWorkerRoutingTests(SimpleTestCase):
    def test_delivery_and_archive_tasks_use_the_notification_worker(self):
        for task in (
            "deliver_transactional_email",
            "deliver_live_class_confirmation",
            "deliver_live_class_reminder",
            "archive_invoice_pdf_task",
            "archive_missing_invoice_pdfs",
        ):
            route = app.amqp.router.route({}, f"content.tasks.{task}")
            self.assertEqual(route["queue"].name, "notifications")


class BookingProductionMigrationTests(TransactionTestCase):
    def test_existing_production_invoice_metadata_survives_booking_migration(self):
        production = [("content", "0007_invoice_pdf_archive")]
        release = [("content", "0010_private_booking_tables")]
        executor = MigrationExecutor(connection)
        executor.migrate(production)
        try:
            apps = executor.loader.project_state(production).apps
            student = apps.get_model("content", "StudentRecord").objects.create(
                supabase_user_id=uuid.uuid4(),
                email="migration@example.test",
                first_name="Synthetic",
                last_name="Migration",
            )
            category = apps.get_model("content", "CourseCategory").objects.create(
                name="Migration rehearsal", slug="migration-rehearsal"
            )
            course = apps.get_model("content", "Course").objects.create(
                category=category, title="Synthetic migration course", slug="synthetic-migration-course", price="950.00"
            )
            payment = apps.get_model("content", "Payment").objects.create(
                reference="PF-MIGRATION-TEST",
                student=student,
                course=course,
                amount="950.00",
                status="paid",
                gateway_verified_at=timezone.now(),
            )
            invoice = apps.get_model("content", "Invoice").objects.create(
                payment=payment,
                invoice_number="INV-PF-MIGRATION-TEST",
                student=student,
                course=course,
                amount="950.00",
                issued_at=timezone.now(),
                pdf_storage_path="synthetic/existing.pdf",
                pdf_sha256="a" * 64,
            )
            executor = MigrationExecutor(connection)
            executor.migrate(release)
            apps = executor.loader.project_state(release).apps
            restored = apps.get_model("content", "Invoice").objects.get(pk=invoice.pk)
            self.assertEqual(restored.pdf_storage_path, "synthetic/existing.pdf")
            self.assertEqual(restored.pdf_sha256, "a" * 64)
            self.assertIn("content_liveclassbooking", connection.introspection.table_names())
            self.assertIn("content_tutoravailabilityslot", connection.introspection.table_names())
        finally:
            MigrationExecutor(connection).migrate(release)
