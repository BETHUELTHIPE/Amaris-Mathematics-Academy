import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import close_old_connections, connection, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from content.models import (
    Course,
    CourseCategory,
    Enrollment,
    LiveClassBooking,
    Payment,
    StudentMotivationEmail,
    StudentRecord,
    TutorAvailabilitySlot,
    VideoRequest,
)
from content.services.student_motivation import (
    deliver_due_email,
    due_registrations,
    ineligible,
    queue_due_emails,
    unsubscribe_token,
)
from content.sponsor_models import SponsorAccount
from content.tasks import deliver_student_motivation_email, queue_student_motivation_emails
from content.tutor_application_models import TutorApplication


@skipUnless(connection.vendor == "postgresql", "Registration source requires PostgreSQL")
@override_settings(
    STUDENT_MOTIVATION_EMAIL_ENABLED=True,
    PUBLIC_SITE_URL="https://students.example.test",
    PUBLIC_API_URL="https://api.example.test",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class StudentMotivationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Synthetic Auth source, isolated in the test database. TestCase rolls
        # the DDL back after the class; no live Supabase accounts are used.
        with connection.cursor() as cursor:
            cursor.execute("CREATE SCHEMA IF NOT EXISTS auth")
            cursor.execute("""CREATE TABLE auth.users (
                id uuid PRIMARY KEY, email text, created_at timestamptz,
                email_confirmed_at timestamptz, deleted_at timestamptz,
                banned_until timestamptz, is_anonymous boolean DEFAULT false,
                raw_app_meta_data jsonb DEFAULT '{}'::jsonb)""")
            cursor.execute("CREATE TABLE public.student_profiles (id uuid PRIMARY KEY, first_name text)")
        category = CourseCategory.objects.create(name="Test", slug="test")
        cls.course = Course.objects.create(
            category=category,
            title="Mathematics",
            slug="test",
            short_description="Test",
            description="Test",
            curriculum="CAPS",
            academic_level="12",
            price="250.00",
        )

    def register(self, *, age=14, verified=True, name="Learner", user_id=None, **updates):
        user_id = user_id or uuid.uuid4()
        email = f"{user_id.hex}@example.test"
        created_at = timezone.now() - timedelta(days=age)
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO auth.users (id,email,created_at,email_confirmed_at) VALUES (%s,%s,%s,%s)",
                [user_id, email, created_at, timezone.now() if verified else None],
            )
            cursor.execute("INSERT INTO public.student_profiles (id,first_name) VALUES (%s,%s)", [user_id, name])
            for key, value in updates.items():
                self.assertIn(key, ("deleted_at", "banned_until", "is_anonymous", "raw_app_meta_data"))
                cursor.execute(f"UPDATE auth.users SET {key} = %s WHERE id = %s", [value, user_id])
        return user_id, email

    def student(self, user_id, email):
        return StudentRecord.objects.create(
            supabase_user_id=user_id, email=email, first_name="Test", last_name="Learner"
        )

    def test_original_registration_date_and_no_return_visit_are_supported(self):
        self.register(age=14)
        self.register(age=13.999)
        self.register(age=20, verified=False)
        self.assertEqual(queue_student_motivation_emails(), 1)
        self.assertEqual(queue_student_motivation_emails(), 0)
        self.assertEqual(StudentRecord.objects.count(), 0)
        self.assertEqual(deliver_student_motivation_email(), 1)
        self.assertEqual(deliver_student_motivation_email(), 0)
        self.assertEqual(queue_student_motivation_emails(), 0)
        receipt = StudentMotivationEmail.objects.get()
        self.assertEqual(receipt.status, "sent")
        self.assertIsNotNone(receipt.sent_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("https://students.example.test/dashboard", mail.outbox[0].body)
        self.assertIn("https://api.example.test/api/v1/emails/motivation/unsubscribe/", mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].reply_to, ["bethuelmoukangwe8@gmail.com"])
        self.assertEqual(len(mail.outbox[0].to), 1)

    def test_exact_fourteen_day_boundary_and_old_backlog(self):
        now = timezone.now()
        self.register(age=45)
        user_id, _ = self.register(age=1)
        with connection.cursor() as cursor:
            cursor.execute("UPDATE auth.users SET created_at=%s WHERE id=%s", [now - timedelta(days=14), user_id])
        with patch("content.services.student_motivation.timezone.now", return_value=now):
            self.assertEqual(len(due_registrations()), 2)
        with patch("content.services.student_motivation.timezone.now", return_value=now - timedelta(microseconds=1)):
            self.assertEqual(len(due_registrations()), 1)

    def test_unverified_deleted_banned_anonymous_and_nonstudent_accounts_are_excluded(self):
        self.register(verified=False)
        self.register(deleted_at=timezone.now())
        self.register(banned_until=timezone.now() + timedelta(days=1))
        self.register(is_anonymous=True)
        self.register(raw_app_meta_data='{"role":"tutor"}')
        self.assertEqual(queue_due_emails(), 0)

    def test_staff_tutor_and_inactive_accounts_are_suppressed(self):
        user_id, email = self.register()
        get_user_model().objects.create_user(username="staff", email=email)
        user_id, email = self.register()
        TutorApplication.objects.create(supabase_user_id=user_id, email=email, experience_years=1)
        user_id, email = self.register()
        student = self.student(user_id, email)
        student.is_active = False
        student.save()
        self.assertEqual(queue_due_emails(), 0)
        self.assertEqual(StudentMotivationEmail.objects.filter(status="suppressed").count(), 3)

    def test_sponsor_accounts_do_not_receive_student_motivation_emails(self):
        for is_active in (True, False):
            user_id, _ = self.register()
            SponsorAccount.objects.create(supabase_user_id=user_id, name="Sponsor", is_active=is_active)
        self.assertEqual(queue_due_emails(), 0)
        self.assertEqual(StudentMotivationEmail.objects.filter(status="suppressed").count(), 2)

    def test_all_course_payment_evidence_and_refunds_suppress(self):
        for evidence in (
            {"status": "paid"},
            {"status": "refunded"},
            {"paid_at": timezone.now()},
            {"gateway_verified_at": timezone.now()},
        ):
            with self.subTest(evidence=evidence):
                user_id, email = self.register()
                student = self.student(user_id, email)
                Payment.objects.create(
                    reference=str(user_id),
                    student=student,
                    course=self.course,
                    amount="250.00",
                    provider="payfast",
                    **evidence,
                )
                self.assertTrue(ineligible(user_id, email))
        self.assertEqual(queue_due_emails(), 0)

    def test_pending_failed_cancelled_payments_do_not_count_as_payment(self):
        for status in ("pending", "failed", "cancelled"):
            user_id, email = self.register()
            student = self.student(user_id, email)
            Payment.objects.create(
                reference=str(user_id),
                student=student,
                course=self.course,
                amount="250.00",
                provider="payfast",
                status=status,
            )
            self.assertFalse(ineligible(user_id, email))
        self.assertEqual(queue_due_emails(), 3)

    def test_paid_live_class_and_video_requests_and_active_enrollment_suppress(self):
        tutor = get_user_model().objects.create_user(username="tutor", email="tutor@example.test")
        slot = TutorAvailabilitySlot.objects.create(
            tutor=tutor,
            programme="caps",
            subject="mathematics",
            level="12",
            starts_at=timezone.now() + timedelta(days=1),
            ends_at=timezone.now() + timedelta(days=1, hours=1),
            zoom_join_url="https://zoom.us/j/123456789",
        )
        for kind in ("live", "video", "enrollment"):
            user_id, email = self.register()
            student = self.student(user_id, email)
            if kind == "live":
                LiveClassBooking.objects.create(
                    student=student,
                    slot=slot,
                    reference="live",
                    idempotency_key="live",
                    programme="caps",
                    subject="mathematics",
                    level="12",
                    topic="Algebra",
                    status="cancelled",
                    paid_at=timezone.now(),
                )
            elif kind == "video":
                VideoRequest.objects.create(
                    student=student,
                    reference="video",
                    idempotency_key="video",
                    programme="caps",
                    subject="mathematics",
                    level="12",
                    topic="Algebra",
                    request_type="chapter_topic",
                    amount="450.00",
                    status="queued",
                )
            else:
                Enrollment.objects.create(student=student, course=self.course, status="active")
            self.assertTrue(ineligible(user_id, email))
        self.assertEqual(queue_due_emails(), 0)

    def test_payment_after_queueing_is_checked_again_before_sending(self):
        user_id, email = self.register()
        self.assertEqual(queue_due_emails(), 1)
        student = self.student(user_id, email)
        Payment.objects.create(
            reference="late-payment",
            student=student,
            course=self.course,
            amount="250.00",
            provider="payfast",
            status="paid",
        )
        self.assertEqual(deliver_due_email(), 0)
        self.assertEqual(StudentMotivationEmail.objects.get().status, "suppressed")
        self.assertEqual(len(mail.outbox), 0)

    def test_auth_is_rechecked_for_deletion_and_email_changes(self):
        user_id, email = self.register()
        queue_due_emails()
        with connection.cursor() as cursor:
            cursor.execute("UPDATE auth.users SET email=%s WHERE id=%s", ["new@example.test", user_id])
        self.assertEqual(deliver_due_email(), 1)
        self.assertEqual(mail.outbox[0].to, ["new@example.test"])
        user_id, email = self.register()
        queue_due_emails()
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM auth.users WHERE id=%s", [user_id])
        self.assertEqual(deliver_due_email(), 0)

    def test_html_escapes_profile_names(self):
        self.register(name='<script>alert("test")</script>')
        queue_due_emails()
        deliver_due_email()
        html = mail.outbox[0].alternatives[0].content
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_smtp_failure_is_visible_without_automatic_duplicate_retry(self):
        self.register()
        queue_due_emails()
        with patch("django.core.mail.EmailMultiAlternatives.send", side_effect=OSError("private detail")):
            self.assertEqual(deliver_due_email(), 0)
        receipt = StudentMotivationEmail.objects.get()
        self.assertEqual(receipt.status, "review")
        self.assertEqual(receipt.last_error_code, "OSError")
        self.assertIsNone(receipt.sent_at)
        self.assertEqual(deliver_due_email(), 0)
        self.assertEqual(queue_due_emails(), 0)

    def test_interrupted_delivery_claim_is_not_automatically_resent(self):
        self.register()
        queue_due_emails()
        StudentMotivationEmail.objects.update(status="sending", attempted_at=timezone.now())
        self.assertEqual(deliver_due_email(), 0)
        self.assertEqual(queue_due_emails(), 0)

    def test_unsubscribe_requires_confirmation_and_valid_signed_token(self):
        user_id, _ = self.register()
        queue_due_emails()
        url = reverse("student-motivation-unsubscribe") + "?token=" + unsubscribe_token(user_id)
        client = Client(enforce_csrf_checks=True)
        response = client.get(url, secure=True)
        self.assertContains(response, '<button type="submit">Unsubscribe</button>')
        self.assertIsNone(StudentMotivationEmail.objects.get().unsubscribed_at)
        self.assertEqual(client.post(url, secure=True).status_code, 403)
        csrf_token = client.cookies["csrftoken"].value
        response = client.post(url, {"csrfmiddlewaretoken": csrf_token}, secure=True, HTTP_ORIGIN="https://testserver")
        self.assertContains(response, "You are unsubscribed")
        self.assertNotContains(response, "&lt;h1&gt;")
        self.assertEqual(response["Referrer-Policy"], "same-origin")
        self.assertEqual(deliver_due_email(), 0)
        self.assertEqual(
            client.post(
                url, {"csrfmiddlewaretoken": csrf_token}, secure=True, HTTP_ORIGIN="https://testserver"
            ).status_code,
            200,
        )
        self.assertEqual(
            client.get(reverse("student-motivation-unsubscribe") + "?token=invalid", secure=True).status_code, 400
        )

    @override_settings(STUDENT_MOTIVATION_EMAIL_ENABLED=False)
    def test_disable_switch_stops_queueing_and_delivery(self):
        self.register()
        self.assertEqual(queue_due_emails(), 0)
        self.assertEqual(deliver_due_email(), 0)

    @override_settings(PUBLIC_API_URL="")
    def test_missing_public_url_does_not_send_or_consume_receipt(self):
        self.register()
        queue_due_emails()
        with self.assertRaises(ValueError):
            deliver_due_email()
        self.assertEqual(StudentMotivationEmail.objects.get().status, "queued")

    def test_beat_uses_existing_notifications_queue(self):
        for name in ("queue-student-motivation-emails", "deliver-student-motivation-email"):
            self.assertEqual(settings.CELERY_BEAT_SCHEDULE[name]["options"]["queue"], "notifications")

    def test_receipts_have_rls_and_no_public_data_api_access(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT relrowsecurity FROM pg_class WHERE oid='content_studentmotivationemail'::regclass")
            self.assertTrue(cursor.fetchone()[0])
            cursor.execute("SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')")
            for (role,) in cursor.fetchall():
                cursor.execute(
                    "SELECT has_table_privilege(%s, 'content_studentmotivationemail', 'SELECT,INSERT,UPDATE,DELETE')",
                    [role],
                )
                self.assertFalse(cursor.fetchone()[0])


@skipUnless(connection.vendor == "postgresql", "Row locking requires PostgreSQL")
@override_settings(STUDENT_MOTIVATION_EMAIL_ENABLED=True)
class StudentMotivationConcurrencyTests(TransactionTestCase):
    def test_second_worker_skips_locked_recipient(self):
        receipt = StudentMotivationEmail.objects.create(supabase_user_id=uuid.uuid4(), registered_at=timezone.now())

        def another_worker():
            close_old_connections()
            try:
                return deliver_due_email()
            finally:
                close_old_connections()

        with transaction.atomic():
            StudentMotivationEmail.objects.select_for_update().get(pk=receipt.pk)
            with ThreadPoolExecutor(max_workers=1) as pool:
                self.assertEqual(pool.submit(another_worker).result(timeout=5), 0)
        receipt.refresh_from_db()
        self.assertEqual(receipt.status, "queued")
