"""Cross-service payment receipt delivery to email and private student dashboard.

All gateway callbacks are synthetic, test DB and local storage are isolated;
no real PayFast wallet, SMTP email, Supabase or production data is touched.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.storage import storages
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from content.authentication import SupabaseStudentPrincipal
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
from content.services.invoices import student_invoice_key
from content.services.live_classes import create_live_class_checkout, process_live_class_notification
from content.services.payments import create_checkout, process_payfast_notification
from content.services.video_requests import create_video_request_checkout, process_video_request_notification
from content.tasks import (
    deliver_live_class_confirmation,
    deliver_transactional_email,
    deliver_video_request_notifications,
)


class VerifiedSyntheticGateway:
    def verify_notification(self, payload):
        return True


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="Amaris Receipt Tests <no-reply@example.test>",
)
class StudentReceiptDeliveryTests(TestCase):
    def setUp(self):
        self.temp_storage = TemporaryDirectory()
        self.addCleanup(self.temp_storage.cleanup)
        self.storage_overrides = override_settings(
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                    "OPTIONS": {"location": str(Path(self.temp_storage.name) / "admin")},
                },
                "student_private": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                    "OPTIONS": {
                        "location": str(Path(self.temp_storage.name) / "student"),
                        "allow_overwrite": True,
                    },
                },
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
            }
        )
        self.storage_overrides.enable()
        self.addCleanup(self.storage_overrides.disable)
        self.student = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(),
            email="receipt.student@example.test",
            first_name="Receipt",
            last_name="Student",
        )
        self.other = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(),
            email="unrelated.student@example.test",
            first_name="Different",
            last_name="Student",
        )
        self.tutor = get_user_model().objects.create_user(
            username="receipt.test.tutor", email="tutor@example.test",
            first_name="Tutor", last_name="Receipt",
        )
        self.start = (timezone.now() + timedelta(days=3)).replace(second=0, microsecond=0)
        self.slot = TutorAvailabilitySlot.objects.create(
            tutor=self.tutor,
            programme=TutorAvailabilitySlot.Programme.CAPS,
            subject=TutorAvailabilitySlot.Subject.MATHEMATICS,
            level="Grade 12",
            starts_at=self.start,
            ends_at=self.start + timedelta(hours=2),
            zoom_join_url="https://zoom.example.test/j/123456789",
            is_active=True,
        )
        category = CourseCategory.objects.create(name="Receipt CI", slug="receipt-ci")
        self.course = Course.objects.create(
            category=category,
            title="Isolated Receipt Mathematics Course",
            slug="isolated-receipt-maths",
            short_description="Synthetic CI payment",
            description="No real student is enrolled",
            curriculum="Mathematics",
            academic_level="Grade 12",
            price=Decimal("950.00"),
            status=Course.Status.PUBLISHED,
        )

    def client_for(self, student):
        client = APIClient()
        client.force_authenticate(user=SupabaseStudentPrincipal(
            student=student, supabase_user_id=str(student.supabase_user_id), email=student.email
        ))
        return client

    def assert_dashboard_and_pdf(self, kind, reference, invoice_number, expected_amount):
        owner = self.client_for(self.student)
        outsider = self.client_for(self.other)
        orders = owner.get(reverse("student-orders"), secure=True)
        self.assertEqual(orders.status_code, 200, orders.data)
        matching = [row for row in orders.data if row["kind"] == kind and row["reference"] == reference]
        self.assertEqual(len(matching), 1)
        order = matching[0]
        self.assertTrue(order["invoice_ready"], order)
        self.assertEqual(str(order["amount"]), expected_amount)
        self.assertEqual(order["invoice_number"], invoice_number)
        if kind == "course":
            route = reverse("student-course-invoice", args=[reference])
        elif kind == "live_class":
            route = reverse("live-class-invoice-download", args=[reference])
        else:
            route = reverse("video-request-invoice", args=[reference])
        self.assertEqual(outsider.get(route, secure=True).status_code, 404)
        response = owner.get(route, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(response["Content-Type"], "application/pdf")
        pdf = b"".join(response.streaming_content)
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertGreater(len(pdf), 1000)
        self.assertFalse(storages["default"].exists(
            student_invoice_key(self.student.supabase_user_id, invoice_number)
        ))
        return pdf

    def assert_mail_and_private_file(self, invoice_number, delivered_pdf):
        self.assertGreaterEqual(len(mail.outbox), 1)
        confirmation = mail.outbox[0]
        self.assertEqual(confirmation.to, [self.student.email])
        self.assertEqual(len(confirmation.attachments), 1)
        filename, attachment, mime = confirmation.attachments[0]
        self.assertEqual(filename, invoice_number + ".pdf")
        self.assertEqual(mime, "application/pdf")
        self.assertEqual(attachment, delivered_pdf)
        self.assertTrue(attachment.startswith(b"%PDF-"))
        # The protected path must exist in the student's bucket, not admin storage.
        storage = storages["student_private"]
        if isinstance(invoice_number, str):
            if invoice_number.startswith("INV-PF-"):
                archived = Invoice.objects.get(invoice_number=invoice_number)
                key = archived.pdf_storage_path
                self.assertTrue(key)
            else:
                key = student_invoice_key(self.student.supabase_user_id, invoice_number)
            self.assertTrue(storage.exists(key), key)
            with storage.open(key, "rb") as file:
                self.assertEqual(file.read(), delivered_pdf)

    def test_course_payment_emails_exact_dashboard_receipt_once(self):
        checkout = create_checkout(
            student=self.student, course=self.course, idempotency_key="receipt-" + "course-20261017"
        )
        payload = {
            "m_payment_id": checkout.payment_reference,
            "pf_payment_id": "SYNTHETIC-PF-RECEIPT-COURSE",
            "payment_status": "COMPLETE",
            "amount_gross": "950.00",
            "custom_str1": str(self.student.supabase_user_id),
            "custom_str2": self.course.slug,
        }
        result = process_payfast_notification(payload, gateway=VerifiedSyntheticGateway())
        self.assertTrue(result.accepted)
        invoice = Invoice.objects.get(payment__reference=checkout.payment_reference)
        self.assertEqual(deliver_transactional_email.run(), 1)
        downloaded = self.assert_dashboard_and_pdf("course", checkout.payment_reference, invoice.invoice_number, "950.00")
        self.assert_mail_and_private_file(invoice.invoice_number, downloaded)
        self.assertEqual(deliver_transactional_email.run(), 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_live_class_pdf_is_available_before_email_and_matches_attachment(self):
        checkout = create_live_class_checkout(
            student=self.student, slot=self.slot, topic="Proof of payment revision",
            idempotency_key="receipt-" + "live-20261017",
        )
        booking = LiveClassBooking.objects.get(reference=checkout.booking_reference)
        payload = {
            "m_payment_id": booking.reference,
            "pf_payment_id": "SYNTHETIC-PF-RECEIPT-LIVE",
            "payment_status": "COMPLETE",
            "amount_gross": "500.00",
            "custom_str1": str(self.student.supabase_user_id),
            "custom_str2": booking.reference,
        }
        result = process_live_class_notification(payload, gateway=VerifiedSyntheticGateway())
        self.assertTrue(result.accepted)
        booking.refresh_from_db()
        self.assertEqual(booking.status, LiveClassBooking.Status.CONFIRMED)
        # Even when SMTP/worker has not run, show the proof in Orders & Payments.
        self.assertIsNone(booking.confirmation_sent_at)
        self.assert_dashboard_and_pdf("live_class", booking.reference, booking.invoice_number, "500.00")
        self.assertEqual(deliver_live_class_confirmation.run(), 1)
        booking.refresh_from_db()
        self.assertIsNotNone(booking.confirmation_sent_at)
        stored = self.assert_dashboard_and_pdf("live_class", booking.reference, booking.invoice_number, "500.00")
        self.assert_mail_and_private_file(booking.invoice_number, stored)
        self.assertEqual(deliver_live_class_confirmation.run(), 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_video_request_pdf_is_available_before_email_and_matches_attachment(self):
        checkout = create_video_request_checkout(
            student=self.student, programme="caps", subject="mathematics",
            level="Grade 12", topic="Differential calculus", request_type="chapter_topic",
            instructions="Synthetic receipt test", explanation_style="Worked examples",
            preferred_duration_minutes=60, idempotency_key="receipt-" + "video-20261017",
            documents=(),
        )
        item = VideoRequest.objects.get(reference=checkout.request_reference)
        payload = {
            "m_payment_id": item.reference,
            "pf_payment_id": "SYNTHETIC-PF-RECEIPT-VIDEO",
            "payment_status": "COMPLETE",
            "amount_gross": "450.00",
            "custom_str1": str(self.student.supabase_user_id),
            "custom_str2": item.reference,
        }
        result = process_video_request_notification(payload, gateway=VerifiedSyntheticGateway())
        self.assertTrue(result.accepted)
        item.refresh_from_db()
        self.assertEqual(item.status, VideoRequest.Status.QUEUED)
        self.assertIsNone(item.confirmation_sent_at)
        self.assert_dashboard_and_pdf("video_request", item.reference, item.invoice_number, "450.00")
        self.assertGreaterEqual(deliver_video_request_notifications.run(), 1)
        item.refresh_from_db()
        self.assertIsNotNone(item.confirmation_sent_at)
        stored = self.assert_dashboard_and_pdf("video_request", item.reference, item.invoice_number, "450.00")
        self.assert_mail_and_private_file(item.invoice_number, stored)
        self.assertEqual(mail.outbox[0].to, [self.student.email])

    def test_unverified_payment_never_exposes_proof_in_dashboard(self):
        checkout = create_checkout(
            student=self.student, course=self.course, idempotency_key="receipt-" + "unpaid-20261017"
        )
        orders = self.client_for(self.student).get(reverse("student-orders"), secure=True)
        matching = [item for item in orders.data if item["reference"] == checkout.payment_reference]
        self.assertEqual(len(matching), 1)
        self.assertFalse(matching[0]["invoice_ready"])
        self.assertIsNone(matching[0]["invoice_number"])
        self.assertEqual(
            self.client_for(self.student).get(
                reverse("student-course-invoice", args=[checkout.payment_reference]), secure=True
            ).status_code,
            404,
        )
        self.assertEqual(deliver_transactional_email.run(), 0)
        self.assertEqual(len(mail.outbox), 0)
