import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from smtplib import SMTPConnectError
from threading import Barrier
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core import mail
from django.core.files.base import ContentFile
from django.core.files.storage import InMemoryStorage
from django.core.mail import EmailMultiAlternatives
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from pypdf import PdfReader

from content.models import (
    Course,
    CourseCategory,
    LiveClassBooking,
    Payment,
    SiteSettings,
    StudentRecord,
    TutorAvailabilitySlot,
    VideoRequest,
)
from content.performance_models import PerformanceDigest, PerformanceSchedule
from content.performance_tasks import process_performance_reports
from content.services.performance_metrics import SAST, bounds, build_snapshot
from content.services.performance_reports import archived_pdf, deliver_report, due_period, generate_due_report


class PerformanceFixtures:
    def setUp(self):
        self.start, self.end = date(2026, 10, 30), date(2026, 11, 13)
        self.lower, self.upper = bounds(self.start, self.end)
        self.now = datetime(2026, 11, 13, 9, 5, tzinfo=SAST)
        self.clock = patch("django.utils.timezone.now", return_value=self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.storage = InMemoryStorage()
        storage = patch.object(PerformanceDigest._meta.get_field("pdf"), "storage", self.storage)
        storage.start()
        self.addCleanup(storage.stop)
        self.group = Group.objects.get_or_create(name="Tutors")[0]
        self.tutor = get_user_model().objects.create_user(
            username="metrics-tutor", first_name="Synthetic", last_name="Tutor"
        )
        self.tutor.groups.add(self.group)
        self.other = get_user_model().objects.create_user(
            username="metrics-other", first_name="Another", last_name="Tutor"
        )
        self.other.groups.add(self.group)
        self.student = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(), email="private.student@example.test", first_name="PrivateStudent"
        )
        self.second_student = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(), email="other.student@example.test"
        )
        category = CourseCategory.objects.create(name="Performance sample", slug="performance-sample")
        self.course = Course.objects.create(
            category=category,
            title="Algebra foundations",
            slug="algebra-foundations",
            short_description="Synthetic test",
            description="Synthetic test",
            curriculum="CAPS",
            academic_level="Grade 11",
            price="250.00",
        )
        SiteSettings.objects.create(email="admin@example.test")
        self.index = 0

    def booking(self, day=1, **changes):
        self.index += 1
        starts = changes.pop("starts", self.lower + timedelta(days=day + 1, hours=self.index))
        tutor = changes.pop("tutor", self.tutor)
        slot = TutorAvailabilitySlot.objects.create(
            tutor=tutor,
            programme="caps",
            subject="mathematics",
            level="Grade 11",
            starts_at=starts,
            ends_at=starts + timedelta(hours=2),
            zoom_join_url="https://zoom.us/j/synthetic",
        )
        values = dict(
            reference=str(uuid.uuid4()),
            idempotency_key=str(uuid.uuid4()),
            student=self.student,
            slot=slot,
            programme="caps",
            subject="mathematics",
            level="Grade 11",
            topic="Quadratic equations",
            amount="500.00",
            currency="ZAR",
            status="confirmed",
            payment_mode="live",
            paid_at=self.lower + timedelta(days=day),
            gateway_verified_at=self.lower + timedelta(days=day),
            hold_expires_at=self.now + timedelta(days=2),
        )
        values.update(changes)
        return LiveClassBooking.objects.create(**values)

    def purchase(self, day=1, **changes):
        values = dict(
            reference=str(uuid.uuid4()),
            student=self.student,
            course=self.course,
            provider="payfast",
            amount="250.00",
            currency="ZAR",
            status="paid",
            payment_mode="live",
            paid_at=self.lower + timedelta(days=day),
            gateway_verified_at=self.lower + timedelta(days=day),
        )
        values.update(changes)
        return Payment.objects.create(**values)

    def video(self, day=1, **changes):
        values = dict(
            reference=str(uuid.uuid4()),
            idempotency_key=str(uuid.uuid4()),
            student=self.student,
            assigned_tutor=self.tutor,
            programme="caps",
            subject="mathematics",
            level="Grade 11",
            topic="Quadratic equations",
            request_type="chapter_topic",
            amount="450.00",
            currency="ZAR",
            status="queued",
            payment_mode="live",
            paid_at=self.lower + timedelta(days=day),
            gateway_verified_at=self.lower + timedelta(days=day),
            ticket_number=str(uuid.uuid4()),
            payment_expires_at=self.now + timedelta(days=2),
        )
        values.update(changes)
        return VideoRequest.objects.create(**values)


@override_settings(
    ADMIN_PERFORMANCE_REPORTS_ENABLED=True,
    ADMIN_PERFORMANCE_PAYMENT_MODE="live",
    ADMIN_PERFORMANCE_ADMIN_EMAIL="",
    ADMIN_PERFORMANCE_START_DATE="2026-10-30",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class PerformanceReportTests(PerformanceFixtures, TestCase):
    def test_rankings_use_verified_orders_and_actual_tutor_identity(self):
        self.booking(status="completed")
        self.booking(student=self.second_student)
        self.booking(tutor=self.other)
        self.purchase()
        self.purchase(student=self.second_student)
        self.video()
        result = build_snapshot(self.start, self.end, "live")
        self.assertEqual(
            result["totals"], {"bookings": 3, "video_requests": 1, "course_purchases": 2, "gross": "2450.00"}
        )
        leader = result["tutors"][0]
        self.assertEqual(leader["name"], "Synthetic Tutor")
        self.assertEqual(leader["count"], 2)
        self.assertEqual(leader["learners"], 2)
        self.assertEqual(leader["booked_hours"], "4.00")
        self.assertEqual(leader["completed_due"], 1)
        self.assertEqual(leader["due"], 2)
        self.assertEqual(result["courses"][0]["learners"], 2)
        self.assertNotIn("private.student@example.test", json.dumps(result))
        self.assertNotIn("PrivateStudent", json.dumps(result))

    def test_sandbox_unknown_cancelled_refunded_unverified_zero_and_wrong_currency_excluded(self):
        self.booking()
        for changes in [
            {"payment_mode": "sandbox"},
            {"payment_mode": "unknown"},
            {"status": "cancelled"},
            {"status": "payment_review"},
            {"gateway_verified_at": None},
            {"paid_at": None},
            {"amount": "0.00"},
            {"currency": "USD"},
        ]:
            self.booking(**changes)
        self.purchase(status="refunded")
        self.purchase(payment_mode="sandbox")
        self.video(payment_mode="unknown")
        result = build_snapshot(self.start, self.end, "live")
        self.assertEqual(result["totals"]["bookings"], 1)
        self.assertEqual(result["totals"]["course_purchases"], 0)
        self.assertEqual(result["totals"]["video_requests"], 0)
        self.assertEqual(result["unclassified_orders"], 2)
        self.assertEqual(result["payment_review_orders"], 1)

    def test_topic_case_and_spacing_group_but_curriculum_level_and_request_type_stay_separate(self):
        self.video(topic="  Quadratic   equations ")
        self.video(topic="quadratic\tequations", student=self.second_student)
        self.video(topic="QUADRATIC equations", programme="ieb")
        self.video(topic="Quadratic equations", level="Grade 12")
        self.video(topic="Quadratic equations", request_type="previous_exam")
        result = build_snapshot(self.start, self.end, "live")
        self.assertEqual(len(result["topics"]), 4)
        self.assertEqual(result["topics"][0]["count"], 2)
        self.assertEqual(result["topics"][0]["learners"], 2)
        self.assertEqual(result["topics"][0]["backlog"], 2)

    def test_periods_are_half_open_sast_and_weeks_add_up(self):
        self.purchase(gateway_verified_at=self.lower, paid_at=self.lower)
        self.purchase(gateway_verified_at=self.upper - timedelta(microseconds=1))
        self.purchase(gateway_verified_at=self.upper)
        self.purchase(gateway_verified_at=self.lower - timedelta(microseconds=1))
        result = build_snapshot(self.start, self.end, "live")
        self.assertEqual(result["totals"]["course_purchases"], 2)
        self.assertEqual(sum(row["course_purchases"] for row in result["weekly"]), 2)
        self.assertEqual(result["previous"]["course_purchases"], 1)
        self.assertEqual(result["courses"][0]["change"], "+100.0% vs previous 14 days")

    def test_ties_share_rank_and_future_lessons_do_not_reduce_completion(self):
        self.booking(status="completed")
        self.booking(tutor=self.other, starts=self.upper + timedelta(days=10))
        result = build_snapshot(self.start, self.end, "live")
        self.assertEqual([row["rank"] for row in result["tutors"]], [1, 1])
        self.assertEqual(result["tutors"][1]["due"], 0)
        self.assertEqual(result["tutors"][1]["completion"], "Not due")

    def test_delivery_leaders_include_earlier_paid_orders_completed_in_period(self):
        self.video(
            day=-3,
            status="ready",
            video_ready_at=self.lower + timedelta(days=2),
            video_external_id="private-example-id",
        )
        result = build_snapshot(self.start, self.end, "live")
        self.assertEqual(result["totals"]["video_requests"], 0)
        self.assertEqual(result["delivery_leaders"][0]["count"], 1)

    def test_empty_report_does_not_invent_winners_and_queries_stay_bounded(self):
        with CaptureQueriesContext(connection) as queries:
            result = build_snapshot(self.start, self.end, "live")
        self.assertEqual(result["tutors"], [])
        self.assertEqual(result["totals"]["gross"], "0.00")
        self.assertEqual(result["changes"]["bookings"], "No activity")
        self.assertEqual(result["unbooked_tutors"], 2)
        self.assertLess(len(queries), 45)

    def test_due_schedule_is_every_fourteen_calendar_days_at_nine_sast(self):
        self.assertIsNone(due_period(self.start, self.upper - timedelta(seconds=1)))
        self.assertIsNone(due_period(self.start, self.upper + timedelta(hours=8, minutes=59)))
        self.assertEqual(due_period(self.start, self.upper + timedelta(hours=9)), (self.start, self.end))
        self.assertEqual(
            due_period(self.start, self.upper + timedelta(days=14, hours=9)), (self.end, self.end + timedelta(days=14))
        )

    def test_first_activation_freezes_anchor_and_does_not_mail_early(self):
        with self.settings(ADMIN_PERFORMANCE_START_DATE=""):
            item, created = generate_due_report()
        self.assertIsNone(item)
        self.assertFalse(created)
        schedule = PerformanceSchedule.objects.get(payment_mode="live")
        self.assertEqual(schedule.anchor_date, self.now.date())
        with patch("django.utils.timezone.now", return_value=self.now + timedelta(days=1)):
            self.assertIsNone(generate_due_report()[0])
        self.assertEqual(PerformanceSchedule.objects.get().anchor_date, self.now.date())

    def test_after_extended_downtime_only_latest_period_is_generated_and_gap_is_visible(self):
        later = self.lower + timedelta(days=45, hours=10)
        with patch("django.utils.timezone.now", return_value=later):
            item, created = generate_due_report()
            self.assertTrue(created)
            self.assertEqual(item.period_start, self.start + timedelta(days=28))
            self.assertEqual(item.snapshot["missing_periods"], 2)
            self.assertEqual(process_performance_reports(), 1)
            self.assertEqual(process_performance_reports(), 0)
        self.assertEqual(PerformanceDigest.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_unknown_mail_backend_result_is_held_for_review(self):
        item, _ = generate_due_report()
        with patch.object(EmailMultiAlternatives, "send", return_value=None):
            self.assertEqual(deliver_report(item.pk), 0)
        item.refresh_from_db()
        self.assertEqual(item.delivery_status, "review")

    def test_archive_email_letterhead_and_duplicate_protection(self):
        self.booking()
        self.purchase()
        self.video()
        first, created = generate_due_report()
        self.assertTrue(created)
        second, created = generate_due_report()
        self.assertFalse(created)
        self.assertEqual(first.pk, second.pk)
        self.assertTrue(first.pdf.name.startswith("admin-performance/live/"))
        original = archived_pdf(first)
        text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(original)).pages)
        for value in [
            "Amaris Mathematics Academy",
            "Most booked tutors",
            "Synthetic Tutor",
            "Algebra foundations",
            str(first.pk),
        ]:
            self.assertIn(value, text)
        self.assertEqual(process_performance_reports(), 1)
        self.assertEqual(process_performance_reports(), 0)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["admin@example.test"])
        self.assertEqual(message.attachments[0].content, original)
        self.assertEqual(message.attachments[1].get("Content-ID"), "<amaris-letterhead-logo>")
        self.assertIn("Official academy communication", message.alternatives[0].content)
        self.assertIn("WITHIN THE FORTNIGHT", message.body)
        self.assertNotIn(self.student.email, message.body)
        self.assertNotIn(first.pdf.name, message.body)

    def test_disabled_feature_creates_and_sends_nothing(self):
        with self.settings(ADMIN_PERFORMANCE_REPORTS_ENABLED=False):
            self.assertEqual(generate_due_report(), (None, False))
            self.assertEqual(process_performance_reports(), 0)
        self.assertEqual(PerformanceDigest.objects.count(), 0)

    def test_storage_failure_rolls_back_snapshot_and_does_not_mail(self):
        with patch.object(self.storage, "save", side_effect=OSError("synthetic unavailable")):
            with self.assertRaises(OSError):
                generate_due_report()
        self.assertEqual(PerformanceDigest.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_smtp_rejection_backoff_and_unknown_acceptance_are_not_blindly_resent(self):
        item, _ = generate_due_report()
        with patch.object(EmailMultiAlternatives, "send", side_effect=SMTPConnectError(421, "synthetic rejected")):
            self.assertEqual(deliver_report(item.pk), 0)
        item.refresh_from_db()
        self.assertEqual(item.delivery_status, "queued")
        self.assertEqual(deliver_report(item.pk), 0)
        PerformanceDigest.objects.filter(pk=item.pk).update(next_attempt_at=self.now - timedelta(seconds=1))
        with patch.object(EmailMultiAlternatives, "send", side_effect=TimeoutError("synthetic uncertain")):
            self.assertEqual(deliver_report(item.pk), 0)
        item.refresh_from_db()
        self.assertEqual(item.delivery_status, "review")
        self.assertEqual(deliver_report(item.pk), 0)

    def test_recipient_or_mode_change_and_corrupt_pdf_require_review(self):
        item, _ = generate_due_report()
        with self.settings(ADMIN_PERFORMANCE_ADMIN_EMAIL="another@example.test"):
            self.assertEqual(deliver_report(item.pk), 0)
        item.refresh_from_db()
        self.assertEqual(item.error_code, "recipient_or_mode_changed")
        PerformanceDigest.objects.filter(pk=item.pk).update(delivery_status="queued")
        self.storage.delete(item.pdf.name)
        self.storage.save(item.pdf.name, ContentFile(b"corrupt"))
        self.assertEqual(deliver_report(item.pk), 0)
        item.refresh_from_db()
        self.assertEqual(item.error_code, "archive_integrity_review")

    def test_stale_claim_and_post_acceptance_database_failure_never_duplicate_email(self):
        item, _ = generate_due_report()
        with patch("django.db.models.query.QuerySet.update", side_effect=RuntimeError("synthetic ack failure")):
            with self.assertRaises(RuntimeError):
                deliver_report(item.pk)
        self.assertEqual(len(mail.outbox), 1)
        PerformanceDigest.objects.filter(pk=item.pk).update(sending_at=self.now - timedelta(hours=2))
        self.assertEqual(process_performance_reports(), 0)
        item.refresh_from_db()
        self.assertEqual(item.delivery_status, "review")
        self.assertEqual(len(mail.outbox), 1)

    def test_admin_dashboard_and_pdf_are_private_and_html_is_escaped(self):
        self.booking()
        self.purchase()
        self.video(topic="<script>synthetic</script>")
        item, _ = generate_due_report()
        admin_user = get_user_model().objects.create_superuser(
            username="performance-admin", email="admin.test@example.test", password="synthetic-local-only"
        )
        self.client.force_login(admin_user)
        url = reverse("admin:content_performancedigest_dashboard")
        response = self.client.get(url, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Most booked tutors")
        self.assertContains(response, "&lt;script&gt;synthetic&lt;/script&gt;")
        self.assertNotContains(response, "<script>synthetic</script>")
        self.assertIn("no-store", response["Cache-Control"])
        pdf = self.client.get(reverse("admin:content_performancedigest_pdf", args=[item.pk]), secure=True)
        self.assertEqual(pdf.content, archived_pdf(item))
        self.assertEqual(pdf["X-Content-Type-Options"], "nosniff")
        directory = os.getenv("PERFORMANCE_DASHBOARD_EVIDENCE_DIR")
        if directory:
            output = Path(directory)
            output.mkdir(parents=True, exist_ok=True)
            (output / "dashboard.html").write_bytes(response.content)
            (output / "performance.pdf").write_bytes(pdf.content)
            self.assertEqual(deliver_report(item.pk), 1)
            html = (
                mail.outbox[-1]
                .alternatives[0]
                .content.replace("cid:amaris-letterhead-logo", "/static/invoice-brand/amaris-academy-icon-192.png")
            )
            (output / "email.html").write_text(html)
        self.tutor.is_staff = True
        self.tutor.save(update_fields=["is_staff"])
        self.tutor.user_permissions.add(Permission.objects.get(codename="view_performancedigest"))
        self.client.force_login(self.tutor)
        self.assertEqual(self.client.get(url, secure=True).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("admin:content_performancedigest_pdf", args=[item.pk]), secure=True).status_code,
            403,
        )
        self.client.logout()
        self.assertEqual(self.client.get(url, secure=True).status_code, 302)

    def test_preview_does_not_archive_or_email_and_saved_snapshot_does_not_change(self):
        admin_user = get_user_model().objects.create_superuser(
            username="preview-admin", email="admin2@example.test", password="synthetic-local-only"
        )
        self.client.force_login(admin_user)
        response = self.client.get(reverse("admin:content_performancedigest_dashboard"), {"preview": "1"}, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PerformanceDigest.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)
        item, _ = generate_due_report()
        original = item.snapshot
        self.purchase()
        again, created = generate_due_report()
        self.assertFalse(created)
        self.assertEqual(again.snapshot, original)

    def test_all_verified_payment_paths_capture_environment_and_replays_do_not_reclassify(self):
        from content.services.live_classes import process_live_class_notification
        from content.services.payments import process_payfast_notification
        from content.services.video_requests import process_video_request_notification

        gateway = SimpleNamespace(verify_notification=lambda _: True)
        course = self.purchase(status="pending", payment_mode="unknown", paid_at=None, gateway_verified_at=None)
        booking = self.booking(
            status="pending_payment",
            payment_mode="unknown",
            paid_at=None,
            gateway_verified_at=None,
            starts=self.now + timedelta(days=5),
        )
        video = self.video(status="pending_payment", payment_mode="unknown", paid_at=None, gateway_verified_at=None)
        for item, path, target, mode_path in [
            (course, process_payfast_notification, self.course.slug, "content.services.payments._payfast_mode"),
            (
                booking,
                process_live_class_notification,
                booking.reference,
                "content.services.live_classes._payfast_mode",
            ),
            (
                video,
                process_video_request_notification,
                video.reference,
                "content.services.video_requests._payfast_mode",
            ),
        ]:
            payload = {
                "m_payment_id": item.reference,
                "pf_payment_id": f"synthetic-{item.pk}",
                "payment_status": "COMPLETE",
                "amount_gross": str(item.amount),
                "custom_str1": str(self.student.supabase_user_id),
                "custom_str2": target,
            }
            with patch(mode_path, return_value="sandbox"):
                result = path(payload, gateway=gateway)
            self.assertTrue(result.accepted)
            item.refresh_from_db()
            self.assertEqual(item.payment_mode, "sandbox")
            with patch(mode_path, return_value="live"):
                path(payload, gateway=gateway)
            item.refresh_from_db()
            self.assertEqual(item.payment_mode, "sandbox")

    def test_old_application_insert_without_new_metadata_uses_database_default(self):
        item = self.purchase()
        fields = [
            field for field in Payment._meta.concrete_fields if not field.primary_key and field.name != "payment_mode"
        ]
        names = [connection.ops.quote_name(field.column) for field in fields]
        selected = ["%s" if field.name == "reference" else connection.ops.quote_name(field.column) for field in fields]
        reference = str(uuid.uuid4())
        table = connection.ops.quote_name(Payment._meta.db_table)
        with connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {table} ({', '.join(names)}) SELECT {', '.join(selected)} FROM {table} WHERE id = %s",
                [reference, item.pk],
            )
        self.assertEqual(Payment.objects.get(reference=reference).payment_mode, "unknown")


@skipUnless(connection.vendor == "postgresql", "PostgreSQL locks and RLS required")
@override_settings(
    ADMIN_PERFORMANCE_REPORTS_ENABLED=True,
    ADMIN_PERFORMANCE_PAYMENT_MODE="live",
    ADMIN_PERFORMANCE_ADMIN_EMAIL="",
    ADMIN_PERFORMANCE_START_DATE="2026-10-30",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class PerformancePostgresTests(PerformanceFixtures, TransactionTestCase):
    def test_overlapping_senders_claim_once_and_private_tables_use_rls(self):
        item, _ = generate_due_report()
        barrier = Barrier(2)

        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return deliver_report(item.pk)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: worker(), range(2)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(len(mail.outbox), 1)
        with connection.cursor() as cursor:
            for table in ("content_performancedigest", "content_performanceschedule"):
                cursor.execute("SELECT relrowsecurity FROM pg_class WHERE oid = %s::regclass", [table])
                self.assertTrue(cursor.fetchone()[0])
                cursor.execute("SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated')")
                for (role,) in cursor.fetchall():
                    cursor.execute("SELECT has_table_privilege(%s,%s,'SELECT')", [role, table])
                    self.assertFalse(cursor.fetchone()[0])
