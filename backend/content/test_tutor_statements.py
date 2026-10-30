"""Regression tests for private 30-day tutor reports, finance semantics and email separation."""

import uuid
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from content.models import LiveClassBooking, StudentRecord, TutorAvailabilitySlot
from content.services.tutor_statements import (
    activity_snapshot,
    archive_statement,
    issue_due_statements,
    render_tutor_statement_pdf,
)
from content.tutor_finance_models import TutorActivityStatement, TutorContract, TutorEarning, TutorPayout
from content.tutor_statement_tasks import deliver_due_tutor_statements, send_statement_recipient


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="Amaris Mathematics Academy <no-reply@example.test>",
    TUTOR_STATEMENT_ADMIN_EMAIL="academy-admin@example.test",
    SUPABASE_S3_ADMIN_BUCKET="amaris-cms-files",
    SUPABASE_S3_ENDPOINT_URL="https://example.supabase.co/storage/v1/s3",
    STORAGES={"default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}},
)
class TutorStatementTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.tutor = User.objects.create_user(
            username="monthly-tutor",
            email="monthly-tutor@example.test",
            password="test-account-only",
            first_name="Monthly",
            last_name="Tutor",
        )
        Group.objects.get_or_create(name="Tutors")[0].user_set.add(self.tutor)
        self.student = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(),
            email="private-student@example.test",
            first_name="Private",
            last_name="Learner",
        )
        self.now = timezone.now()
        self.contract = TutorContract.objects.create(
            tutor=self.tutor,
            service=TutorContract.Service.LIVE_CLASS,
            tutor_percent=Decimal("60.00"),
            effective_from=self.now - timedelta(days=50),
            contract_reference="PRIVATE-CONTRACT-001",
        )
        start = self.now - timedelta(days=3)
        self.slot = TutorAvailabilitySlot.objects.create(
            tutor=self.tutor,
            programme=TutorAvailabilitySlot.Programme.CAPS,
            subject=TutorAvailabilitySlot.Subject.MATHEMATICS,
            level="Grade 12",
            starts_at=start,
            ends_at=start + timedelta(hours=2),
            zoom_join_url="https://zoom.us/j/111111111",
        )
        self.booking = LiveClassBooking.objects.create(
            reference="PRIVATE-LIVE-001",
            idempotency_key="tutor-report-private-class-001",
            student=self.student,
            slot=self.slot,
            programme=self.slot.programme,
            subject=self.slot.subject,
            level="Grade 12",
            topic="Differential calculus",
            amount=Decimal("500.00"),
            status=LiveClassBooking.Status.COMPLETED,
            paid_at=start,
            gateway_verified_at=start,
        )
        self.earning = TutorEarning.objects.create(
            tutor=self.tutor,
            contract=self.contract,
            service=TutorContract.Service.LIVE_CLASS,
            source_reference=self.booking.reference,
            service_label="Online class",
            gross=Decimal("500.00"),
            tutor_percent=Decimal("60.00"),
            tutor_amount=Decimal("300.00"),
            academy_amount=Decimal("200.00"),
            payment_verified_at=start,
            service_delivered_at=self.slot.ends_at,
            state=TutorEarning.State.READY,
        )

    def _report(self):
        start = self.now - timedelta(days=30)
        end = self.now + timedelta(minutes=1)
        return TutorActivityStatement.objects.create(
            tutor=self.tutor,
            period_start=start,
            period_end=end,
            report_number=f"ATS-TEST-{self.tutor.pk}",
            snapshot=activity_snapshot(self.tutor, start, end),
        )

    def test_snapshot_counts_students_classes_hours_and_verified_contract_splits(self):
        statement = self._report()
        d = statement.snapshot
        self.assertEqual(d["unique_students"], 1)
        self.assertEqual(d["students_taught"], 1)
        self.assertEqual(d["sessions_taught"], 1)
        self.assertEqual(d["hours_taught"], 2)
        self.assertEqual(d["gross_verified"], "500.00")
        self.assertEqual(d["tutor_share"], "300.00")
        self.assertEqual(d["academy_share"], "200.00")
        self.assertEqual(d["ready_earnings"], "300.00")
        self.assertEqual(d["confirmed_payouts_in_period"], "0.00")
        self.assertNotIn(self.student.email, str(d))
        self.assertNotIn("zoom.us", str(d))

    def test_paid_payout_only_when_provider_confirms_transfer(self):
        TutorPayout.objects.create(
            earning=self.earning,
            state=TutorPayout.State.AWAITING_PROVIDER,
            provider_reference="",
        )
        self.assertEqual(self._report().snapshot["confirmed_payouts_in_period"], "0.00")
        payout = self.earning.payout
        payout.state = TutorPayout.State.PAID
        payout.provider_reference = "CONFIRMED-TRANSFER-123"
        payout.confirmed_at = self.now
        payout.save()
        self.assertEqual(
            activity_snapshot(self.tutor, self.now - timedelta(days=30), self.now + timedelta(days=1))[
                "confirmed_payouts_in_period"
            ],
            "300.00",
        )

    def test_pdf_is_branded_a4_and_student_contact_not_present(self):
        statement = self._report()
        pdf = render_tutor_statement_pdf(statement)
        self.assertTrue(pdf.startswith(b"%PDF"))
        reader = PdfReader(BytesIO(pdf))
        self.assertEqual(round(float(reader.pages[0].mediabox.width)), 595)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        self.assertIn("Amaris Mathematics Academy", text)
        self.assertIn("TUTOR ACTIVITY", text)
        self.assertIn("Completed teaching sessions", text)
        self.assertNotIn(self.student.email, text)
        self.assertNotIn("zoom.us", text)

    def test_archive_is_private_and_each_role_emailed_once(self):
        statement = self._report()
        archive_statement(statement)
        self.assertTrue(statement.pdf_storage_path.startswith("tutor-statements/"))
        self.assertTrue(statement.pdf_sha256)
        self.assertEqual(send_statement_recipient(statement.pk, "tutor"), True)
        self.assertEqual(send_statement_recipient(statement.pk, "tutor"), False)
        self.assertEqual(send_statement_recipient(statement.pk, "admin"), True)
        self.assertEqual(send_statement_recipient(statement.pk, "admin"), False)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].to, [self.tutor.email])
        self.assertEqual(mail.outbox[1].to, ["academy-admin@example.test"])
        for message in mail.outbox:
            self.assertEqual(message.attachments[0][2], "application/pdf")
            self.assertNotIn(self.student.email, message.body)
        statement.refresh_from_db()
        self.assertEqual(statement.state, TutorActivityStatement.State.DELIVERED)
        self.assertIsNotNone(statement.tutor_emailed_at)
        self.assertIsNotNone(statement.admin_emailed_at)

    def test_retry_recovers_only_missing_admin_message(self):
        statement = self._report()
        archive_statement(statement)
        send_statement_recipient(statement.pk, "tutor")
        self.assertEqual(deliver_due_tutor_statements(), 1)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(deliver_due_tutor_statements(), 0)
        self.assertEqual(len(mail.outbox), 2)

    def test_daily_beat_creates_only_contiguous_thirty_day_periods(self):
        self.assertEqual(issue_due_statements(self.now), 1)
        self.assertEqual(issue_due_statements(self.now), 0)
        first = TutorActivityStatement.objects.get()
        self.assertEqual(first.period_end - first.period_start, timedelta(days=30))
        self.assertEqual(issue_due_statements(self.now + timedelta(days=15)), 0)
        self.assertEqual(issue_due_statements(self.now + timedelta(days=31)), 1)
        last = TutorActivityStatement.objects.order_by("-period_end").first()
        self.assertEqual(last.period_start, first.period_end)
        self.assertEqual(last.period_end - last.period_start, timedelta(days=30))

    def test_non_superusers_cannot_view_or_download_ledger(self):
        statement = self._report()
        archive_statement(statement)
        url = reverse("admin:content_tutoractivitystatement_download", args=[statement.pk])
        self.client.force_login(self.tutor)
        self.assertNotEqual(self.client.get(url, secure=True).status_code, 200)
        self.tutor.is_staff = True
        self.tutor.save(update_fields=["is_staff"])
        self.assertEqual(self.client.get(url, secure=True).status_code, 403)
        superuser = get_user_model().objects.create_superuser(
            username="statement-admin", email="statement-admin@example.test", password="test-only-secret"
        )
        self.client.force_login(superuser)
        response = self.client.get(url, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_report_never_initiates_or_marks_a_bank_payout(self):
        statement = self._report()
        archive_statement(statement)
        send_statement_recipient(statement.pk, "tutor")
        send_statement_recipient(statement.pk, "admin")
        self.assertFalse(TutorPayout.objects.exists())
        self.earning.refresh_from_db()
        self.assertEqual(self.earning.state, TutorEarning.State.READY)
