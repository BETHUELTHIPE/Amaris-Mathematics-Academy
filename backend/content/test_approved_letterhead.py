"""Invoice-template regression tests: never deliver legacy generic PDF archives."""

from decimal import Decimal

from django.test import TestCase

from content.services.approved_invoice_letterhead import (
    LegacyInvoiceLetterheadError,
    require_approved_invoice_letterhead,
)
from content.services.invoice_document import (
    InvoiceDocument,
    InvoiceLine,
    render_document,
)


class ApprovedInvoiceLetterheadTests(TestCase):
    def test_actual_professional_renderer_emits_approved_metadata(self):
        document = InvoiceDocument(
            number="INV-TEST-APPROVED-001",
            issue_date="28 October 2026",
            student_name="Synthetic Learner",
            student_email="synthetic@example.test",
            reference="synthetic-verified-payment",
            currency="ZAR",
            lines=(
                InvoiceLine(
                    description="Three-hour Mathematics live class",
                    details=("CAPS Mathematics",),
                    quantity=Decimal("3"),
                    unit_price=Decimal("250.00"),
                ),
            ),
            total=Decimal("750.00"),
        )
        pdf = render_document(document)
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertIn(b"/Author (Amaris Mathematics Academy)", pdf)
        require_approved_invoice_letterhead(pdf)

    def test_legacy_generic_reportlab_invoice_is_not_accepted(self):
        old_pdf = b"%PDF-1.4\n/Author (anonymous)\n"
        with self.assertRaisesRegex(LegacyInvoiceLetterheadError, "approved Amaris letterhead"):
            require_approved_invoice_letterhead(old_pdf)

    def test_forged_non_pdf_with_author_name_is_not_accepted(self):
        with self.assertRaises(LegacyInvoiceLetterheadError):
            require_approved_invoice_letterhead(b"/Author (Amaris Mathematics Academy)")

    def test_unverified_or_blank_file_is_not_accepted(self):
        for raw in (b"", b"<html>invoice</html>", b"%PDF-1.4\n"):
            with self.subTest(raw=raw):
                with self.assertRaises(LegacyInvoiceLetterheadError):
                    require_approved_invoice_letterhead(raw)
