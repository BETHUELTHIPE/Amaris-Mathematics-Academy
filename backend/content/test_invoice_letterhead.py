from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from pypdf import PdfReader

from content.models import (
    Course,
    CourseCategory,
    LiveClassBooking,
    Payment,
    StudentRecord,
    TutorAvailabilitySlot,
    VideoRequest,
)
from content.payment_models import Invoice
from content.services.invoice_document import InvoiceDocument, InvoiceLine, render_document
from content.services.invoices import render_invoice_pdf


class InvoiceLetterheadTests(TestCase):
    def setUp(self):
        self.student = StudentRecord.objects.create(
            supabase_user_id="00000000-0000-4000-8000-000000000812",
            email="preview.student@example.test",
            first_name="Zoë",
            last_name="Ndlovu",
        )
        self.now = timezone.now()

    def documents(self):
        category = CourseCategory.objects.create(name="Letterhead tests", slug="letterhead-tests")
        course = Course.objects.create(
            category=category,
            title="Mathematics mastery",
            slug="letterhead-course",
            price=Decimal("950.00"),
        )
        payment = Payment.objects.create(
            student=self.student,
            course=course,
            reference="PF-letterhead-course",
            amount=course.price,
            status=Payment.Status.PAID,
            gateway_verified_at=self.now,
            paid_at=self.now,
        )
        course_invoice = Invoice.objects.create(
            payment=payment,
            student=self.student,
            course=course,
            invoice_number="INV-LETTERHEAD-COURSE",
            amount=course.price,
            issued_at=self.now,
        )
        tutor = get_user_model().objects.create_user(
            username="letterhead-tutor", first_name="Preview", last_name="Tutor"
        )
        slot = TutorAvailabilitySlot.objects.create(
            tutor=tutor,
            programme="caps",
            subject="mathematics",
            level="Grade 12",
            starts_at=self.now + timedelta(days=2),
            ends_at=self.now + timedelta(days=2, hours=3),
        )
        booking = LiveClassBooking.objects.create(
            student=self.student,
            slot=slot,
            reference="LCB-letterhead-live",
            idempotency_key="letterhead-live",
            programme="caps",
            subject="mathematics",
            level="Grade 12",
            topic="Differential calculus",
            amount=Decimal("750.00"),
            status=LiveClassBooking.Status.CONFIRMED,
            paid_at=self.now,
            gateway_verified_at=self.now,
            invoice_number="INV-LETTERHEAD-LIVE",
        )
        video = VideoRequest.objects.create(
            student=self.student,
            reference="VRQ-letterhead-video",
            idempotency_key="letterhead-video",
            programme="caps",
            subject="mathematics",
            level="Grade 12",
            topic="Sequences and series",
            request_type=VideoRequest.RequestType.CHAPTER_TOPIC,
            amount=Decimal("450.00"),
            status=VideoRequest.Status.QUEUED,
            paid_at=self.now,
            gateway_verified_at=self.now,
            invoice_number="INV-LETTERHEAD-VIDEO",
            ticket_number="VIDEO-letterhead",
        )
        return (course_invoice, booking, video)

    def test_all_services_embed_logo_and_the_complete_professional_letterhead(self):
        for invoice in self.documents():
            with self.subTest(service=type(invoice).__name__):
                document = render_invoice_pdf(invoice)
                reader = PdfReader(BytesIO(document))
                self.assertEqual(len(reader.pages), 1)
                text = reader.pages[0].extract_text()
                for expected in (
                    "Amaris Mathematics Academy",
                    "Managing Director: Bethuel Moukangwe",
                    "BILLED TO",
                    "Zoë Ndlovu",
                    "27 Tshivhase Street",
                    "bethuelmoukangwe8@gmail.com",
                    "071 415 6665",
                    "Description",
                    "Qty",
                    "Unit price",
                    "PAYMENT NOTE",
                    "NEED HELP?",
                    invoice.invoice_number,
                ):
                    self.assertIn(expected, text)
                self.assertIn("amaris-mathematics-academy.bethuelthipe.chatgpt.site", text.replace("\n", ""))
                self.assertGreater(len(reader.pages[0].images), 0)
                # A retry must not produce a different PDF for the same record.
                self.assertEqual(document, render_invoice_pdf(invoice))
        live_pdf = PdfReader(BytesIO(render_invoice_pdf(LiveClassBooking.objects.get())))
        self.assertIn("R 250.00", live_pdf.pages[0].extract_text())
        self.assertIn("R 750.00", live_pdf.pages[0].extract_text())

    def test_long_unicode_content_flows_without_truncation_and_repeats_branding(self):
        invoice = InvoiceDocument(
            number="INV-LONG-" + "1234567890" * 10,
            issue_date="24 October 2026",
            student_name="Zoë Людмила <Student>",
            student_email="preview.student@example.test",
            reference="PF-long-layout",
            currency="ZAR",
            total=Decimal("250.00"),
            lines=(
                InvoiceLine(
                    description="Mathematics and mathematical notation α + β",
                    details=tuple(f"Chapter {i}: " + "Extended mathematics explanation " * 8 for i in range(35))
                    + ("END OF ALL INVOICE DETAILS",),
                    quantity=Decimal("1"),
                    unit_price=Decimal("250.00"),
                ),
            ),
        )
        reader = PdfReader(BytesIO(render_document(invoice)))
        self.assertGreater(len(reader.pages), 1)
        text = "\n".join(page.extract_text() for page in reader.pages)
        self.assertIn("Zoë Людмила <Student>", text)
        self.assertIn("END OF ALL INVOICE DETAILS", text)
        for page in reader.pages:
            self.assertIn("Managing Director: Bethuel Moukangwe", page.extract_text())
            self.assertGreater(len(page.images), 0)
