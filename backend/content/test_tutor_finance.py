"""Tutor finance safeguards: verified revenue, split maths, idempotency, privacy, encrypted bank data."""

import uuid
from datetime import timedelta
from decimal import Decimal

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from content.models import Course, CourseCategory, Payment, StudentRecord
from content.services.payments import create_checkout, process_payfast_notification
from content.services.topical_videos import create_video_checkout, process_video_notification
from content.services.tutor_finance import record_course_sale, tutor_dashboard_stats
from content.tutor_finance_admin import TutorPaymentProfileForm
from content.tutor_finance_models import (
    TutorContract,
    TutorCourseAssignment,
    TutorEarning,
    TutorPayout,
)
from content.tutor_finance_tasks import email_tutor_payout_receipt


class VerifiedGateway:
    def __init__(self, accepted=True):
        self.accepted = accepted

    def verify_notification(self, payload):
        return self.accepted


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class TutorRevenueTests(TestCase):
    def setUp(self):
        self.tutor = get_user_model().objects.create_user(
            username="tutor.ana",
            password="secure-tutor-test-password",
            email="tutor.ana@example.test",
            first_name="Ana",
            last_name="Tutor",
        )
        self.other = get_user_model().objects.create_user(username="uncontracted.tutor", password="password")
        self.student = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(),
            email="private.student@example.test",
            first_name="HiddenStudent",
            last_name="Student",
        )
        category = CourseCategory.objects.create(name="Finance test", slug="finance-test")
        self.course = Course.objects.create(
            category=category,
            title="Calculus",
            slug="finance-calculus",
            short_description="Test",
            description="Test",
            curriculum="CAPS",
            academic_level="Grade 12",
            price=Decimal("250.00"),
            status=Course.Status.PUBLISHED,
        )
        self.contract = TutorContract.objects.create(
            tutor=self.tutor,
            service=TutorContract.Service.COURSE,
            tutor_percent=Decimal("60.00"),
            effective_from=timezone.now() - timedelta(days=1),
            contract_reference="TEST-60-40",
        )
        TutorCourseAssignment.objects.create(course=self.course, tutor=self.tutor)

    def pay_course(self):
        checkout = create_checkout(
            student=self.student,
            course=self.course,
            idempotency_key="finance-course-001",
        )
        payload = {
            "m_payment_id": checkout.payment_reference,
            "pf_payment_id": "FINANCE-PF-001",
            "payment_status": "COMPLETE",
            "amount_gross": "250.00",
            "custom_str1": str(self.student.supabase_user_id),
            "custom_str2": self.course.slug,
        }
        return process_payfast_notification(payload, gateway=VerifiedGateway())

    def test_verified_payment_snapshots_60_40_and_callback_is_idempotent(self):
        self.assertTrue(self.pay_course().accepted)
        earning = TutorEarning.objects.get()
        self.assertEqual(earning.tutor_amount, Decimal("150.00"))
        self.assertEqual(earning.academy_amount, Decimal("100.00"))
        self.assertEqual(earning.tutor_percent, Decimal("60.00"))
        self.assertEqual(earning.state, TutorEarning.State.HELD)
        payment = Payment.objects.get(reference=earning.source_reference)
        record_course_sale(payment)
        self.assertEqual(TutorEarning.objects.count(), 1)
        self.assertEqual(TutorPayout.objects.count(), 0)

    def test_unverified_callback_creates_no_tutor_income(self):
        session = create_checkout(student=self.student, course=self.course, idempotency_key="finance-denied-001")
        response = process_payfast_notification(
            {
                "m_payment_id": session.payment_reference,
                "pf_payment_id": "BAD-PF-001",
                "payment_status": "COMPLETE",
                "amount_gross": "250.00",
                "custom_str1": str(self.student.supabase_user_id),
                "custom_str2": self.course.slug,
            },
            gateway=VerifiedGateway(False),
        )
        self.assertFalse(response.accepted)
        self.assertFalse(TutorEarning.objects.exists())

    def test_snapshot_unchanged_after_contract_edit(self):
        self.pay_course()
        self.contract.tutor_percent = Decimal("50.00")
        self.contract.save()
        earning = TutorEarning.objects.get()
        self.assertEqual(earning.tutor_amount, Decimal("150.00"))

    def test_tutor_dashboard_hides_student_identity_and_bank_account(self):
        self.pay_course()
        self.client.force_login(self.tutor)
        response = self.client.get("/tutor/dashboard/", secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Courses sold")
        self.assertContains(response, "My financial processing status")
        self.assertEqual(response.context["processing"]["held"], 1)
        self.assertEqual(response.context["processing"]["paid"], 0)
        self.assertContains(response, "R 150.00")
        self.assertNotContains(response, self.student.email)
        self.assertNotContains(response, self.student.first_name)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get("/tutor/dashboard/", secure=True).status_code, 403)

    def test_processing_status_does_not_include_another_tutors_records(self):
        self.pay_course()
        other_contract = TutorContract.objects.create(
            tutor=self.other,
            service=TutorContract.Service.COURSE,
            tutor_percent=Decimal("50.00"),
            effective_from=timezone.now() - timedelta(days=1),
            contract_reference="TEST-OTHER-50",
        )
        TutorEarning.objects.create(
            tutor=self.other, contract=other_contract,
            service=TutorContract.Service.COURSE,
            source_reference="private-other-tutor-sale",
            service_label="Private sale",
            gross=Decimal("100.00"),
            tutor_percent=Decimal("50.00"),
            tutor_amount=Decimal("50.00"),
            academy_amount=Decimal("50.00"),
            payment_verified_at=timezone.now(),
            state=TutorEarning.State.READY,
        )
        self.client.force_login(self.tutor)
        response = self.client.get("/tutor/dashboard/", secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["processing"]["held"], 1)
        self.assertEqual(response.context["processing"]["ready"], 0)
        self.assertNotContains(response, "private-other-tutor-sale")

    def test_payout_email_requires_confirmed_transfer(self):
        self.pay_course()
        earning = TutorEarning.objects.get()
        payout = TutorPayout.objects.create(earning=earning)
        self.assertEqual(email_tutor_payout_receipt.run(), 0)
        self.assertEqual(len(mail.outbox), 0)
        payout.state = TutorPayout.State.PAID
        payout.provider_name = "verified-bank-provider"
        payout.provider_reference = "TRANSFER-TEST-001"
        payout.confirmed_at = timezone.now()
        payout.bank_last_four = "1234"
        payout.save()
        self.assertEqual(email_tutor_payout_receipt.run(), 1)
        self.assertEqual(email_tutor_payout_receipt.run(), 0)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("R 150.00", mail.outbox[0].body)
        self.assertNotIn(self.student.email, mail.outbox[0].body)

    def test_account_numbers_are_encrypted_and_write_only(self):
        with override_settings(TUTOR_BANK_FERNET_KEY=Fernet.generate_key().decode()):
            form = TutorPaymentProfileForm(
                data={
                    "tutor": str(self.tutor.pk),
                    "account_holder": "Ana Tutor",
                    "bank_name": "Example Bank",
                    "branch_code": "000000",
                    "account_number": "1234567890",
                    "is_active": False,
                }
            )
            self.assertTrue(form.is_valid(), form.errors)
            profile = form.save()
            self.assertNotIn("1234567890", profile.encrypted_account_number)
            self.assertEqual(profile.account_last_four, "7890")
            self.assertEqual(profile.is_active, False)

    def test_paid_video_sale_creates_one_request_and_revenue_event(self):
        TutorContract.objects.create(
            tutor=self.tutor,
            service=TutorContract.Service.VIDEO,
            tutor_percent=Decimal("50.00"),
            effective_from=timezone.now() - timedelta(days=1),
            contract_reference="TEST-50-50",
        )
        session = create_video_checkout(
            student=self.student,
            tutor=self.tutor,
            topic="Quadratics",
            programme="CAPS Grade 12",
            idempotency_key="finance-video-001",
        )
        result = process_video_notification(
            {
                "m_payment_id": session.payment_reference,
                "pf_payment_id": "VIDEO-PF-001",
                "payment_status": "COMPLETE",
                "amount_gross": session.fields["amount"],
                "custom_str1": str(self.student.supabase_user_id),
                "custom_str2": session.payment_reference,
            },
            gateway=VerifiedGateway(),
        )
        self.assertTrue(result.accepted)
        earning = TutorEarning.objects.get()
        self.assertEqual(earning.service, TutorContract.Service.VIDEO)
        self.assertEqual(earning.tutor_amount, Decimal("225.00"))
        self.assertEqual(tutor_dashboard_stats(self.tutor)["categories"]["video"]["count"], 1)
