import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from smtplib import SMTPConnectError
from threading import Barrier
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import InMemoryStorage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError, close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader
from rest_framework.test import APIClient

from content.authentication import SupabaseStudentAuthentication
from content.models import Course, CourseCategory, CourseModule, Enrollment, Lesson, StudentRecord
from content.services.subscription_reports import (
    capture_study_activity,
    date_label,
    deliver_report,
    prepare_report,
    report_snapshot,
    save_session,
)
from content.services.subscriptions import add_calendar_months
from content.subscription_models import CurriculumSubscription
from content.subscription_report_models import SubscriptionReport, SubscriptionSession, SubscriptionStudyActivity
from content.subscription_report_tasks import deliver_ended_subscription_reports


class ReportFixtures:
    def setUp(self):
        self.mode = patch.dict(os.environ, {"PAYFAST_MODE": "sandbox"})
        self.mode.start()
        self.addCleanup(self.mode.stop)
        self.storage = InMemoryStorage()
        for module in ["content.services.subscription_reports", "content.subscription_report_views"]:
            mock = patch(module + ".storages", {"student_private": self.storage})
            mock.start()
            self.addCleanup(mock.stop)
        self.student = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(), first_name="Lerato", last_name="Mokoena", email="learner@example.test"
        )
        self.tutor = get_user_model().objects.create_user(
            username="report-tutor", first_name="Amaris", last_name="Tutor", email="tutor@example.test"
        )
        self.tutor.groups.add(Group.objects.get_or_create(name="Tutors")[0])
        end = timezone.now() - timedelta(seconds=1)
        self.sub = CurriculumSubscription.objects.create(
            student=self.student,
            reference="SUB-REPORT-TEST",
            idempotency_key="report-test-key",
            curriculum="caps",
            months=4,
            amount="3800",
            status="paid",
            gateway_mode="sandbox",
            gateway_verified_at=add_calendar_months(end, -4),
            starts_at=add_calendar_months(end, -4),
            ends_at=end,
        )
        category = CourseCategory.objects.create(name="Mathematics", slug="report-maths")
        course = Course.objects.create(
            category=category,
            title="Algebra foundations",
            slug="report-course",
            curriculum="CAPS",
            price="950",
            status="published",
            is_published=True,
        )
        module = CourseModule.objects.create(course=course, title="Algebra", is_published=True)
        lesson = Lesson.objects.create(
            module=module, title="Quadratic equations", slug="report-lesson", is_published=True
        )
        self.enrollment = Enrollment.objects.create(
            student=self.student,
            course=course,
            status="active",
            subscription_access=self.sub,
            progress_percent=60,
            last_lesson=lesson,
        )
        SubscriptionStudyActivity.objects.create(
            subscription=self.sub,
            enrollment=self.enrollment,
            occurred_at=self.sub.starts_at + timedelta(days=3),
            course_title=course.title,
            lesson_title=lesson.title,
            progress_percent=60,
            kind="progress",
        )
        self.api = APIClient(HTTP_X_FORWARDED_PROTO="https")
        self.api.force_authenticate(
            user=SimpleNamespace(student=self.student, pk=self.student.pk, is_authenticated=True)
        )

    def session(self, status="planned", day=2, **kwargs):
        start = self.sub.starts_at + timedelta(days=day)
        item = SubscriptionSession(
            subscription=self.sub,
            tutor=self.tutor,
            starts_at=start,
            ends_at=start + timedelta(hours=2),
            subject="Mathematics",
            level="Grade 11",
            topic="Quadratic equations",
            status=status,
            **kwargs,
        )
        if status in {"attended", "partial"}:
            item.joined_at = start + (timedelta(minutes=30) if status == "partial" else timedelta())
            item.left_at = item.ends_at
        return save_session(item, self.tutor)


@override_settings(
    SUBSCRIPTION_REPORTS_EMAIL_ENABLED=True, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
)
class SubscriptionReportTests(ReportFixtures, TestCase):
    def test_actual_pdf_email_contains_precise_attendance_and_sast_ledger_once(self):
        self.session(
            "attended",
            learning_summary="Solved quadratic equations",
            tutor_feedback="Strong factorisation",
            next_steps="Practise completing the square",
        )
        self.session("partial", day=3)
        self.session("absent", day=4)
        self.session("planned", day=5)
        self.session("cancelled", day=6)
        self.assertEqual(deliver_ended_subscription_reports()["sent"], 1)
        self.assertEqual(deliver_ended_subscription_reports()["sent"], 0)
        report = self.sub.final_report
        self.assertEqual(report.status, "sent")
        self.assertEqual(report.snapshot["attended_minutes"], 210)
        self.assertEqual(report.snapshot["scheduled_minutes"], 480)
        self.assertEqual(report.snapshot["attendance_percent"], 58.3)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.student.email])
        self.assertEqual(mail.outbox[0].cc, [])
        self.assertEqual(mail.outbox[0].bcc, [])
        attachment = mail.outbox[0].attachments[0]
        pdf = attachment[1]
        reader = PdfReader(BytesIO(pdf))
        text = "\n".join(page.extract_text() for page in reader.pages)
        for expected in [
            "Lerato Mokoena",
            "3h 30m",
            "Quadratic equations",
            "Grade 11",
            "Amaris Tutor",
            "Practise completing the square",
            "60%",
            "South African time",
            "not an assessment",
        ]:
            self.assertIn(expected, text)
        self.assertGreaterEqual(len(reader.pages), 2)
        self.assertIn(str(self.student.supabase_user_id), report.pdf_storage_path)
        self.assertEqual(self.storage.open(report.pdf_storage_path).read(), pdf)
        if preview := os.getenv("AMARIS_REPORT_PREVIEW"):
            Path(preview).parent.mkdir(parents=True, exist_ok=True)
            Path(preview).write_bytes(pdf)

    def test_report_waits_for_end_and_verified_payment_and_active_student(self):
        original = {key: getattr(self.sub, key) for key in ["ends_at", "status", "gateway_mode", "gateway_verified_at"]}
        for changes in [
            {"ends_at": timezone.now() + timedelta(days=1)},
            {"status": "pending"},
            {"status": "refunded"},
            {"gateway_mode": "live"},
            {"gateway_verified_at": None},
        ]:
            for key, value in {**original, **changes}.items():
                setattr(self.sub, key, value)
            self.sub.save()
            self.assertEqual(deliver_ended_subscription_reports()["sent"], 0)
            self.assertFalse(SubscriptionReport.objects.exists())
        for key, value in original.items():
            setattr(self.sub, key, value)
        self.sub.save()
        self.student.is_active = False
        self.student.save()
        self.assertEqual(deliver_ended_subscription_reports()["sent"], 0)

    @override_settings(SUBSCRIPTION_REPORTS_EMAIL_ENABLED=False)
    def test_flag_off_has_no_delivery_or_archive_side_effects(self):
        self.assertEqual(deliver_ended_subscription_reports()["sent"], 0)
        self.assertFalse(SubscriptionReport.objects.exists())

    def test_eight_month_subscription_is_included(self):
        self.sub.months, self.sub.amount = 8, "7600"
        self.sub.starts_at = add_calendar_months(self.sub.ends_at, -8)
        self.sub.save()
        self.assertEqual(deliver_ended_subscription_reports()["sent"], 1)
        self.assertEqual(self.sub.final_report.snapshot["months"], 8)

    def test_no_attendance_records_are_not_claimed_as_absence(self):
        report = prepare_report(self.sub.pk)
        self.assertIsNone(report.snapshot["attendance_percent"])
        self.assertEqual(report.snapshot["attended_minutes"], 0)
        self.assertEqual(report.snapshot["counts"]["absent"], 0)

    def test_unknown_smtp_result_is_held_and_never_automatically_resent(self):
        report = prepare_report(self.sub.pk)
        with patch(
            "content.services.subscription_reports.EmailMultiAlternatives.send", side_effect=TimeoutError
        ) as send:
            self.assertEqual(deliver_report(report.pk), 0)
            self.assertEqual(deliver_ended_subscription_reports()["sent"], 0)
            self.assertEqual(send.call_count, 1)
        report.refresh_from_db()
        self.assertEqual(report.status, "review")
        self.assertEqual(report.error_code, "smtp_outcome_unknown")

    def test_known_rejection_retries_with_backoff_and_stops_after_five(self):
        report = prepare_report(self.sub.pk)
        with patch(
            "content.services.subscription_reports.EmailMultiAlternatives.send",
            side_effect=SMTPConnectError(421, b"not accepted"),
        ) as send:
            for _attempt in range(5):
                SubscriptionReport.objects.filter(pk=report.pk).update(next_attempt_at=None)
                self.assertEqual(deliver_report(report.pk), 0)
                self.assertEqual(deliver_report(report.pk), 0)
            self.assertEqual(send.call_count, 5)
        report.refresh_from_db()
        self.assertEqual(report.status, "review")

    def test_accepted_email_followed_by_database_failure_keeps_durable_claim(self):
        report = prepare_report(self.sub.pk)
        with patch("content.services.subscription_reports.SubscriptionReport.objects.filter") as query:
            query.return_value.update.side_effect = OperationalError("simulated commit failure")
            with self.assertRaises(OperationalError):
                deliver_report(report.pk)
        self.assertEqual(len(mail.outbox), 1)
        report.refresh_from_db()
        self.assertEqual(report.status, "sending")
        self.assertEqual(deliver_report(report.pk), 0)
        SubscriptionReport.objects.filter(pk=report.pk).update(delivery_started_at=timezone.now() - timedelta(hours=2))
        deliver_ended_subscription_reports()
        report.refresh_from_db()
        self.assertEqual(report.status, "review")
        with self.assertRaises(CommandError):
            call_command("review_subscription_report_delivery", str(report.pk))

    def test_changed_recipient_and_tampered_archive_require_review(self):
        report = prepare_report(self.sub.pk)
        self.storage.delete(report.pdf_storage_path)
        self.storage.save(report.pdf_storage_path, ContentFile(b"not the archived report"))
        self.assertEqual(deliver_report(report.pk), 0)
        report.refresh_from_db()
        self.assertEqual(report.error_code, "archive_integrity")
        report.status, report.recipient = "ready", "another@example.test"
        report.save()
        self.assertEqual(deliver_report(report.pk), 0)
        report.refresh_from_db()
        self.assertEqual(report.error_code, "recipient_changed")

    def test_private_owner_download_and_other_students_and_anonymous_denied(self):
        prepare_report(self.sub.pk)
        url = reverse("subscription-report", kwargs={"reference": self.sub.reference})
        response = self.api.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF"))
        other = StudentRecord.objects.create(supabase_user_id=uuid.uuid4(), email="other@example.test")
        self.api.force_authenticate(user=SimpleNamespace(student=other, pk=other.pk, is_authenticated=True))
        self.assertEqual(self.api.get(url).status_code, 404)
        self.assertEqual(APIClient(HTTP_X_FORWARDED_PROTO="https").get(url).status_code, 401)

    def test_only_assigned_tutor_can_confirm_and_list_sessions(self):
        item = self.session()
        url = reverse("subscription-attendance", kwargs={"session_id": item.pk})
        other = get_user_model().objects.create_user(username="other-tutor")
        self.api.force_authenticate(user=other)
        self.assertEqual(self.api.patch(url, {"status": "absent"}).status_code, 404)
        self.assertEqual(self.api.get(reverse("subscription-tutor-sessions")).data["results"], [])
        self.api.force_authenticate(user=self.tutor)
        self.assertEqual(self.api.patch(url, {"status": "absent"}).status_code, 200)
        result = self.api.get(reverse("subscription-tutor-sessions"))
        self.assertEqual(len(result.data["results"]), 1)
        self.assertNotIn(self.student.email, str(result.data))
        client = APIClient(HTTP_X_FORWARDED_PROTO="https")
        payload = {
            "id": str(self.student.supabase_user_id),
            "email": self.student.email,
            "email_confirmed_at": "2026-01-01",
        }
        with patch.object(SupabaseStudentAuthentication, "_validate_token", return_value=payload):
            self.assertEqual(
                client.patch(url, {"status": "absent"}, HTTP_AUTHORIZATION="Bearer student").status_code, 401
            )

    def test_invalid_partial_windows_overlap_and_future_confirmation_rejected(self):
        item = self.session("attended")
        item.joined_at = item.starts_at - timedelta(minutes=1)
        with self.assertRaises(ValidationError):
            save_session(item, self.tutor)
        with self.assertRaises(ValidationError):
            self.session(day=2)
        item.joined_at, item.status = None, "absent"
        with self.assertRaises(ValidationError):
            save_session(item, self.tutor)

    def test_activity_records_milestones_only_within_the_matching_subscription(self):
        SubscriptionStudyActivity.objects.all().delete()
        now = self.sub.starts_at + timedelta(days=10)
        with patch("content.services.subscription_reports.timezone.now", return_value=now):
            capture_study_activity(self.enrollment)
            self.enrollment.last_position_seconds = 120
            capture_study_activity(self.enrollment)
            self.assertEqual(SubscriptionStudyActivity.objects.count(), 1)
            self.enrollment.progress_percent = 80
            capture_study_activity(self.enrollment)
        self.assertEqual(SubscriptionStudyActivity.objects.count(), 2)
        capture_study_activity(self.enrollment)  # Ended subscriptions cannot add activities.
        self.assertEqual(SubscriptionStudyActivity.objects.count(), 2)

    def test_snapshot_survives_renewal_and_late_correction_without_silent_replacement(self):
        item = self.session("attended")
        report = prepare_report(self.sub.pk)
        before = report.pdf_sha256
        item.tutor_feedback = "Late correction"
        save_session(item, self.tutor)
        self.enrollment.subscription_access = None
        self.enrollment.progress_percent = 99
        self.enrollment.save()
        again = prepare_report(self.sub.pk)
        self.assertEqual(again.pdf_sha256, before)
        self.assertEqual(again.snapshot["courses"][0]["percent"], 60)

    def test_sast_calendar_rollover_is_explicit(self):
        self.assertEqual(date_label(datetime(2026, 7, 31, 23, tzinfo=UTC)), "Sat 01 Aug 2026, 01:00")

    def test_progress_api_captures_subscription_milestones_without_counting_playback_hours(self):
        self.sub.starts_at = timezone.now() - timedelta(days=7)
        self.sub.ends_at = add_calendar_months(self.sub.starts_at, 4)
        self.sub.save()
        before = SubscriptionStudyActivity.objects.count()
        payload = {
            "course_slug": self.enrollment.course.slug,
            "lesson_slug": self.enrollment.last_lesson.slug,
            "progress_percent": 75,
            "position_seconds": 900,
        }
        self.assertEqual(self.api.patch(reverse("student-progress"), payload, format="json").status_code, 200)
        self.assertEqual(SubscriptionStudyActivity.objects.count(), before + 1)
        self.assertEqual(self.api.patch(reverse("student-progress"), payload, format="json").status_code, 200)
        self.assertEqual(SubscriptionStudyActivity.objects.count(), before + 1)
        latest = SubscriptionStudyActivity.objects.latest("pk")
        self.assertEqual(latest.progress_percent, 75)
        self.assertEqual(report_snapshot(self.sub, uuid.uuid4())["attended_minutes"], 0)

    def test_course_access_is_not_study_but_authorized_lesson_opens_are_dated(self):
        self.sub.starts_at = timezone.now() - timedelta(days=7)
        self.sub.ends_at = add_calendar_months(self.sub.starts_at, 4)
        self.sub.save()
        SubscriptionStudyActivity.objects.all().delete()
        self.assertEqual(self.api.get(reverse("student-courses")).status_code, 200)
        self.assertFalse(SubscriptionStudyActivity.objects.exists())
        url = reverse(
            "student-lesson",
            kwargs={"course_slug": self.enrollment.course.slug, "lesson_slug": self.enrollment.last_lesson.slug},
        )
        self.assertEqual(self.api.get(url).status_code, 200)
        self.assertEqual(self.api.get(url).status_code, 200)
        self.assertEqual(SubscriptionStudyActivity.objects.count(), 1)
        self.assertEqual(SubscriptionStudyActivity.objects.get().kind, "lesson_opened")

    def test_refund_after_preparation_suppresses_delivery_and_stale_edits_are_rejected(self):
        session = self.session()
        stale = SubscriptionSession.objects.get(pk=session.pk)
        session.topic = "Updated topic"
        save_session(session, self.tutor)
        with self.assertRaises(ValidationError):
            save_session(stale, self.tutor)
        report = prepare_report(self.sub.pk)
        self.sub.status = "refunded"
        self.sub.save()
        self.assertEqual(deliver_report(report.pk), 0)

    def test_long_student_facing_notes_and_markup_render_as_plain_text(self):
        self.session(
            "attended",
            learning_summary=("A < B & revision " * 60)[:1000],
            tutor_feedback=("Long explanatory feedback. " * 40)[:1000],
            next_steps=("Practise with your workbook. " * 40)[:1000],
        )
        report = prepare_report(self.sub.pk)
        pdf = self.storage.open(report.pdf_storage_path).read()
        text = " ".join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)
        self.assertIn("A < B & revision", text)
        self.assertIn("Practise with your workbook", text)


@skipUnless(connection.vendor == "postgresql", "Real row-lock and RLS checks require PostgreSQL")
@override_settings(
    SUBSCRIPTION_REPORTS_EMAIL_ENABLED=True, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
)
class SubscriptionReportPostgresTests(ReportFixtures, TransactionTestCase):
    def test_two_workers_make_only_one_smtp_attempt(self):
        report = prepare_report(self.sub.pk)
        barrier = Barrier(2)

        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return deliver_report(report.pk)
            finally:
                close_old_connections()

        with patch("content.services.subscription_reports.EmailMultiAlternatives.send", return_value=1) as send:
            with ThreadPoolExecutor(max_workers=2) as workers:
                results = list(workers.map(lambda _: worker(), range(2)))
        self.assertEqual(sorted(results), [0, 1])
        self.assertEqual(send.call_count, 1)

    def test_private_report_tables_have_rls_and_no_public_select_grant(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relname, relrowsecurity FROM pg_class WHERE relname IN "
                "('content_subscriptionreport', 'content_subscriptionsession', 'content_subscriptionstudyactivity')"
            )
            rows = cursor.fetchall()
            self.assertEqual(len(rows), 3)
            self.assertTrue(all(row[1] for row in rows))
            cursor.execute(
                "SELECT COUNT(*) FROM pg_class c, LATERAL aclexplode(c.relacl) a WHERE c.relname IN "
                "('content_subscriptionreport', 'content_subscriptionsession', 'content_subscriptionstudyactivity') "
                "AND a.grantee = 0 AND a.privilege_type = 'SELECT'"
            )
            self.assertEqual(cursor.fetchone()[0], 0)
