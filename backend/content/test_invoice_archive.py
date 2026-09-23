from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

from django.core.files.storage import InMemoryStorage
from django.test import TestCase
from django.utils import timezone

from content.models import Course, CourseCategory, Payment, StudentRecord
from content.payment_models import Invoice
from content.services.invoices import InvoiceArchiveError, archive_invoice_pdf, invoice_storage_path
from content.services.payments import create_checkout, process_payfast_notification


class _VerifiedGateway:
    def verify_notification(self, payload):
        del payload
        return True


class InvoiceArchiveTests(TestCase):
    def setUp(self):
        self.student = StudentRecord.objects.create(
            supabase_user_id=uuid.UUID("00000000-0000-4000-8000-000000000711"),
            email="invoice.student@example.test",
            first_name="Invoice",
            last_name="Student",
        )
        category = CourseCategory.objects.create(name="Invoice Tests", slug="invoice-tests")
        self.course = Course.objects.create(
            category=category,
            title="Synthetic Mathematics Mastery",
            slug="synthetic-mathematics-mastery",
            short_description="Synthetic invoice fixture",
            description="No real student or payment data is used.",
            curriculum="Synthetic",
            academic_level="Test",
            price=Decimal("950.00"),
            status=Course.Status.PUBLISHED,
            is_published=True,
        )

    def _paid_invoice(self):
        paid_at = timezone.now()
        payment = Payment.objects.create(
            reference="PF-invoice-archive-001",
            student=self.student,
            course=self.course,
            provider=Payment.Provider.PAYFAST,
            provider_reference="PF-SYNTHETIC-ARCHIVE-001",
            amount=self.course.price,
            currency="ZAR",
            status=Payment.Status.PAID,
            paid_at=paid_at,
            gateway_verified_at=paid_at,
            verification_source="synthetic_test",
        )
        invoice = Invoice.objects.create(
            payment=payment,
            invoice_number=f"INV-{payment.reference}",
            student=self.student,
            course=self.course,
            amount=payment.amount,
            currency=payment.currency,
            issued_at=paid_at,
        )
        return payment, invoice

    def test_paid_invoice_pdf_is_archived_under_student_uuid_idempotently(self):
        _payment, invoice = self._paid_invoice()
        storage = InMemoryStorage()

        first_path = archive_invoice_pdf(invoice.pk, storage=storage)
        second_path = archive_invoice_pdf(invoice.pk, storage=storage)

        expected = invoice_storage_path(invoice)
        self.assertEqual(first_path, expected)
        self.assertEqual(second_path, expected)
        self.assertTrue(storage.exists(expected))

        with storage.open(expected, "rb") as archived:
            payload = archived.read()
        self.assertTrue(payload.startswith(b"%PDF"))
        self.assertGreater(len(payload), 1500)

        invoice.refresh_from_db()
        self.assertEqual(invoice.pdf_storage_path, expected)
        self.assertEqual(len(invoice.pdf_sha256), 64)
        self.assertIsNotNone(invoice.pdf_generated_at)
        self.assertEqual(invoice.pdf_last_error_code, "")

        _dirs, files = storage.listdir(f"{self.student.supabase_user_id}/invoices")
        self.assertEqual(files, [f"{invoice.invoice_number}.pdf"])

    def test_unverified_or_unpaid_invoice_cannot_be_archived(self):
        payment = Payment.objects.create(
            reference="PF-invoice-unverified-001",
            student=self.student,
            course=self.course,
            provider=Payment.Provider.PAYFAST,
            amount=self.course.price,
            currency="ZAR",
            status=Payment.Status.PENDING,
        )
        invoice = Invoice.objects.create(
            payment=payment,
            invoice_number=f"INV-{payment.reference}",
            student=self.student,
            course=self.course,
            amount=payment.amount,
            currency=payment.currency,
            issued_at=timezone.now(),
        )

        with self.assertRaises(InvoiceArchiveError):
            archive_invoice_pdf(invoice.pk, storage=InMemoryStorage())

    def test_verified_payment_queues_pdf_archive_only_after_commit(self):
        checkout = create_checkout(
            student=self.student,
            course=self.course,
            idempotency_key="invoice-payment-queue-001",
        )
        callback = {
            "m_payment_id": checkout.payment_reference,
            "pf_payment_id": "PF-SANDBOX-INVOICE-QUEUE-001",
            "payment_status": "COMPLETE",
            "amount_gross": "950.00",
            "custom_str1": str(self.student.supabase_user_id),
            "custom_str2": self.course.slug,
            "signature": "synthetic-signature-never-sent",
        }

        with patch("content.tasks.archive_invoice_pdf_task.delay") as delayed:
            with self.captureOnCommitCallbacks(execute=True):
                result = process_payfast_notification(callback, gateway=_VerifiedGateway())

        self.assertTrue(result.accepted)
        invoice = Invoice.objects.get(payment__reference=checkout.payment_reference)
        delayed.assert_called_once_with(invoice.pk)
        self.assertEqual(invoice.pdf_storage_path, "")

    def test_broker_outage_archives_verified_invoice_synchronously(self):
        _payment, invoice = self._paid_invoice()
        storage = InMemoryStorage()

        with patch("content.tasks.archive_invoice_pdf_task.delay", side_effect=ConnectionError("broker down")):
            with patch(
                "content.services.invoices.archive_invoice_pdf",
                side_effect=lambda invoice_id: archive_invoice_pdf(invoice_id, storage=storage),
            ):
                from content.services.payments import _queue_invoice_archive

                _queue_invoice_archive(invoice.pk)

        invoice.refresh_from_db()
        self.assertEqual(invoice.pdf_storage_path, invoice_storage_path(invoice))
        self.assertTrue(storage.exists(invoice.pdf_storage_path))

    def test_broker_and_storage_outage_records_failure_without_rolling_back_payment(self):
        _payment, invoice = self._paid_invoice()

        with patch("content.tasks.archive_invoice_pdf_task.delay", side_effect=ConnectionError("broker down")):
            with patch("content.services.invoices.archive_invoice_pdf", side_effect=OSError("storage down")):
                from content.services.payments import _queue_invoice_archive

                _queue_invoice_archive(invoice.pk)

        invoice.refresh_from_db()
        self.assertEqual(invoice.pdf_storage_path, "")
        self.assertEqual(invoice.pdf_last_error_code, "OSError")
