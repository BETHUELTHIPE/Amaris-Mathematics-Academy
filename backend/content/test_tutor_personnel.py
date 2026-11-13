import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO
from smtplib import SMTPConnectError
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core import mail
from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import InMemoryStorage
from django.core.mail import EmailMultiAlternatives
from django.db import close_old_connections, connection
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader
from rest_framework.test import APIClient

from content.models import SiteSettings
from content.services.tutor_personnel import archived_pdf, deliver_form, submit_form
from content.services.tutor_video_uploads import UploadConflict
from content.tutor_personnel_admin import TutorPersonnelFormAdmin
from content.tutor_personnel_models import TutorPersonnelForm
from content.tutor_personnel_tasks import deliver_tutor_personnel_forms


class PersonnelFixtures:
    def setUp(self):
        caches["default"].clear()
        self.tutor = get_user_model().objects.create_user(
            username="personnel-tutor", email="tutor@example.test", first_name="Tutor", last_name="Example"
        )
        self.group = Group.objects.get_or_create(name="Tutors")[0]
        self.tutor.groups.add(self.group)
        SiteSettings.objects.create(email="admin@example.test")
        self.storage = InMemoryStorage()
        storage_patch = patch.object(TutorPersonnelForm._meta.get_field("pdf"), "storage", self.storage)
        storage_patch.start()
        self.addCleanup(storage_patch.stop)
        self.api = APIClient(HTTP_X_FORWARDED_PROTO="https")
        self.api.force_authenticate(user=self.tutor)
        self.today = timezone.localdate()
        self.values = {
            "kind": "leave",
            "leave_type": "study",
            "start_date": self.today + timedelta(days=1),
            "end_date": self.today + timedelta(days=3),
            "reason": "Preparing for final examinations.",
            "handover": "No lessons are affected during this leave period.",
            "contact_phone": "+27 71 234 5678",
            "signature_name": "Tutor Example",
            "declaration": True,
        }

    def submit(self, key="synthetic-leave-key", **changes):
        return submit_form(tutor=self.tutor, key=key, values={**self.values, **changes})

    def post(self, **changes):
        values = {**self.values, "idempotency_key": "synthetic-personnel-api", **changes}
        return self.api.post(reverse("tutor-personnel-forms"), values, format="json")


@override_settings(
    TUTOR_PERSONNEL_FORMS_ENABLED=True,
    TUTOR_PERSONNEL_ADMIN_EMAIL="",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class TutorPersonnelTests(PersonnelFixtures, TestCase):
    def test_leave_saved_in_private_archive_and_admin_detailed_letterhead_pdf_email_once(self):
        item, created = self.submit()
        self.assertTrue(created)
        self.assertEqual(item.status, "submitted")
        self.assertEqual(item.payload["calendar_days"], "3")
        self.assertTrue(item.pdf.name.startswith(f"tutor-personnel/{self.tutor.pk}/{item.pk}/"))
        pdf = archived_pdf(item)
        text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)
        for value in [
            "Amaris Mathematics Academy",
            "Leave application",
            "Tutor Example",
            "Study leave",
            "TYPED SIGNATURE",
            "SAST (UTC+2)",
            str(item.pk),
            "Confidential tutor personnel record",
        ]:
            self.assertIn(value, text)
        self.assertEqual(deliver_tutor_personnel_forms(), 1)
        self.assertEqual(deliver_tutor_personnel_forms(), 0)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["admin@example.test"])
        self.assertEqual(message.cc, [])
        self.assertEqual(message.bcc, [])
        self.assertEqual(message.attachments[0].content, pdf)
        self.assertEqual(message.attachments[0].mimetype, "application/pdf")
        self.assertEqual(message.attachments[1].get("Content-ID"), "<amaris-letterhead-logo>")
        self.assertIn("Official academy communication", message.alternatives[0].content)
        self.assertIn("cid:amaris-letterhead-logo", message.alternatives[0].content)
        self.assertIn("Tutor email: tutor@example.test", message.body)
        self.assertIn("Affected lessons and handover plan", message.body)
        self.assertNotIn(item.pdf.name, message.body)
        self.assertEqual(message.extra_headers["Message-ID"], f"<tutor-form-{item.pk}@amaris.academy>")

    def test_resignation_saved_without_disabling_account_or_cancelling_lessons(self):
        values = {k: v for k, v in self.values.items() if k not in ("leave_type", "start_date", "end_date")}
        values.update(kind="resignation", last_teaching_day=self.today + timedelta(days=30))
        response = self.api.post(
            reverse("tutor-personnel-forms"), {**values, "idempotency_key": "resignation-test-key"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        item = TutorPersonnelForm.objects.get(pk=response.data["id"])
        self.assertEqual(item.kind, "resignation")
        self.assertEqual(item.status, "submitted")
        self.tutor.refresh_from_db()
        self.assertTrue(self.tutor.is_active)
        self.assertTrue(self.tutor.groups.filter(name="Tutors").exists())
        self.assertEqual(deliver_form(item.pk), 1)
        self.assertIn("proposed last teaching day".lower(), mail.outbox[0].body.lower())
        self.assertIn("Withdrawal / resignation notice", mail.outbox[0].alternatives[0].content)

    def test_interrupted_retry_same_payload_returns_original_pdf_and_one_email(self):
        first, _ = self.submit()
        second, created = self.submit()
        self.assertFalse(created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.pdf.name, second.pdf.name)
        with self.assertRaises(UploadConflict):
            self.submit(reason="Different reason using the same submission key.")
        self.assertEqual(TutorPersonnelForm.objects.count(), 1)
        self.assertEqual(deliver_form(first.pk), 1)
        self.assertEqual(deliver_form(second.pk), 0)

    def test_resignation_retry_after_midnight_returns_the_already_saved_notice(self):
        values = {k: v for k, v in self.values.items() if k not in ("leave_type", "start_date", "end_date")}
        values.update(kind="resignation", last_teaching_day=self.today, idempotency_key="midnight-resignation-key")
        original = self.api.post(reverse("tutor-personnel-forms"), values, format="json")
        self.assertEqual(original.status_code, 201)
        with patch("django.utils.timezone.localdate", return_value=self.today + timedelta(days=1)):
            retry = self.api.post(reverse("tutor-personnel-forms"), values, format="json")
            changed = self.api.post(
                reverse("tutor-personnel-forms"),
                {**values, "reason": "Changed details on the same key."},
                format="json",
            )
            new_past_notice = self.api.post(
                reverse("tutor-personnel-forms"), {**values, "idempotency_key": "new-past-resignation"}, format="json"
            )
        self.assertEqual(retry.status_code, 200, retry.data)
        self.assertEqual(retry.data["id"], original.data["id"])
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(new_past_notice.status_code, 400)
        self.assertEqual(TutorPersonnelForm.objects.count(), 1)

    def test_ownership_ignores_client_tutor_and_recipient_status_and_is_private(self):
        other = get_user_model().objects.create_user(username="other-tutor", email="other@example.test")
        other.groups.add(self.group)
        response = self.post(tutor=other.pk, recipient="attacker@example.test", status="approved")
        self.assertEqual(response.status_code, 201)
        item = TutorPersonnelForm.objects.get()
        self.assertEqual(item.tutor, self.tutor)
        self.assertEqual(item.recipient, "admin@example.test")
        self.assertEqual(item.status, "submitted")
        self.assertNotIn("pdf_sha256", response.data)
        self.assertNotIn("recipient", response.data)
        self.assertIn("no-store", response["Cache-Control"])
        own_pdf = self.api.get(reverse("tutor-personnel-pdf", args=[item.pk]))
        self.assertEqual(own_pdf.status_code, 200)
        self.assertEqual(bytes(own_pdf.content), archived_pdf(item))
        self.assertEqual(own_pdf["X-Content-Type-Options"], "nosniff")
        self.api.force_authenticate(user=other)
        self.assertEqual(self.api.get(reverse("tutor-personnel-forms")).data["results"], [])
        self.assertEqual(self.api.get(reverse("tutor-personnel-pdf", args=[item.pk])).status_code, 404)
        self.api.force_authenticate(user=None)
        self.assertEqual(self.api.get(reverse("tutor-personnel-forms")).status_code, 401)

    def test_unapproved_tutor_authentication_and_service_revocation(self):
        self.tutor.groups.clear()
        with self.assertRaises(ValidationError):
            self.submit()
        token = {"id": str(uuid.uuid4()), "email": self.tutor.email, "email_confirmed_at": "2026-01-01T00:00:00Z"}
        self.api.force_authenticate(user=None)
        with patch("content.tutor_views.SupabaseStudentAuthentication._validate_token", return_value=token):
            self.api.credentials(HTTP_AUTHORIZATION="Bearer synthetic-token")
            self.assertEqual(self.api.get(reverse("tutor-personnel-forms")).status_code, 401)
        token["email_confirmed_at"] = None
        self.tutor.groups.add(self.group)
        with patch("content.tutor_views.SupabaseStudentAuthentication._validate_token", return_value=token):
            self.assertEqual(self.api.get(reverse("tutor-personnel-forms")).status_code, 401)

    def test_invalid_dates_declaration_type_and_lengths_do_not_create_records(self):
        for changes in [
            {"end_date": self.today - timedelta(days=1)},
            {"declaration": False},
            {"reason": "short"},
            {"signature_name": "x"},
            {"contact_phone": "<script>"},
            {"leave_type": "invalid"},
            {"last_teaching_day": self.today},
            {"end_date": self.today + timedelta(days=400)},
        ]:
            with self.subTest(changes=changes):
                self.assertEqual(self.post(**changes).status_code, 400)
        for day in [None, str(self.today - timedelta(days=1))]:
            values = {k: v for k, v in self.values.items() if k not in ("leave_type", "start_date", "end_date")}
            values.update(kind="resignation", last_teaching_day=day, idempotency_key="invalid-resignation")
            self.assertEqual(self.api.post(reverse("tutor-personnel-forms"), values, format="json").status_code, 400)
        self.assertEqual(TutorPersonnelForm.objects.count(), 0)

    @override_settings(TUTOR_PERSONNEL_FORMS_ENABLED=False)
    def test_feature_off_prevents_submissions(self):
        self.assertEqual(self.post().status_code, 503)
        self.assertEqual(TutorPersonnelForm.objects.count(), 0)

    def test_private_archive_failure_never_queues_email_or_claims_success(self):
        with patch.object(self.storage, "save", side_effect=OSError("synthetic unavailable")):
            self.assertEqual(self.post().status_code, 503)
        self.assertEqual(TutorPersonnelForm.objects.count(), 0)
        self.assertEqual(deliver_tutor_personnel_forms(), 0)

    def test_transaction_failure_cleans_saved_pdf(self):
        with patch.object(TutorPersonnelForm, "save", side_effect=RuntimeError("synthetic database error")):
            with self.assertRaises(RuntimeError):
                self.submit()
        self.assertEqual(TutorPersonnelForm.objects.count(), 0)
        self.assertEqual(self.storage.listdir(f"tutor-personnel/{self.tutor.pk}")[1], [])

    def test_corrupt_archive_blocks_download_and_delivery(self):
        item, _ = self.submit()
        self.storage.delete(item.pdf.name)
        self.storage.save(item.pdf.name, ContentFile(b"synthetic corrupt document"))
        self.assertEqual(self.api.get(reverse("tutor-personnel-pdf", args=[item.pk])).status_code, 503)
        self.assertEqual(deliver_form(item.pk), 0)
        item.refresh_from_db()
        self.assertEqual(item.delivery_status, "review")
        self.assertEqual(len(mail.outbox), 0)

    def test_admin_recipient_change_holds_confidential_form_for_review(self):
        item, _ = self.submit()
        with self.settings(TUTOR_PERSONNEL_ADMIN_EMAIL="new-admin@example.test"):
            self.assertEqual(deliver_form(item.pk), 0)
        item.refresh_from_db()
        self.assertEqual(item.error_code, "admin_recipient_changed")
        self.assertEqual(item.delivery_status, "review")

    def test_known_rejection_retries_with_backoff_unknown_outcome_never_blindly_resends(self):
        item, _ = self.submit()
        with patch.object(EmailMultiAlternatives, "send", side_effect=SMTPConnectError(421, "synthetic rejection")):
            self.assertEqual(deliver_form(item.pk), 0)
        item.refresh_from_db()
        self.assertEqual(item.delivery_status, "queued")
        self.assertEqual(deliver_form(item.pk), 0)
        TutorPersonnelForm.objects.filter(pk=item.pk).update(next_attempt_at=timezone.now() - timedelta(seconds=1))
        with patch.object(EmailMultiAlternatives, "send", side_effect=TimeoutError("synthetic uncertain acceptance")):
            self.assertEqual(deliver_form(item.pk), 0)
        self.assertEqual(deliver_form(item.pk), 0)
        item.refresh_from_db()
        self.assertEqual(item.delivery_status, "review")
        self.assertEqual(item.attempts, 2)

    def test_stale_claim_and_post_send_db_failure_are_held_not_resent(self):
        item, _ = self.submit()
        with patch(
            "django.db.models.query.QuerySet.update", side_effect=RuntimeError("synthetic acknowledgement failure")
        ):
            with self.assertRaises(RuntimeError):
                deliver_form(item.pk)
        item.refresh_from_db()
        self.assertEqual(item.delivery_status, "sending")
        self.assertEqual(len(mail.outbox), 1)
        TutorPersonnelForm.objects.filter(pk=item.pk).update(sending_at=timezone.now() - timedelta(hours=2))
        self.assertEqual(deliver_tutor_personnel_forms(), 0)
        item.refresh_from_db()
        self.assertEqual(item.delivery_status, "review")
        self.assertEqual(len(mail.outbox), 1)

    def test_escaped_long_content_paginates_and_letterhead_repeats(self):
        item, _ = self.submit(
            reason=("<script> No HTML execution. " * 100)[:2900], handover=("Long handover details. " * 130)[:2900]
        )
        document = PdfReader(BytesIO(archived_pdf(item)))
        self.assertGreater(len(document.pages), 1)
        for page in document.pages:
            text = page.extract_text()
            self.assertIn("Amaris Mathematics Academy", text)
            self.assertIn(str(item.pk), text)
        self.assertEqual(deliver_form(item.pk), 1)
        self.assertIn("&lt;script&gt;", mail.outbox[0].alternatives[0].content)
        self.assertNotIn("<script>", mail.outbox[0].alternatives[0].content)

    def test_admin_review_retains_original_pdf_and_tutor_sees_status(self):
        item, _ = self.submit()
        original_pdf = archived_pdf(item)
        reviewer = get_user_model().objects.create_superuser(
            username="personnel-admin", email="reviewer@example.test", password="synthetic-local-only"
        )
        model_admin = TutorPersonnelFormAdmin(TutorPersonnelForm, admin.site)
        request = RequestFactory().get("/admin/")
        request.user = reviewer
        item.status, item.review_notes = "approved", "Leave approved. Handover confirmed."
        model_admin.save_model(request, item, None, True)
        item.refresh_from_db()
        self.assertEqual(item.reviewed_by, reviewer)
        self.assertEqual(archived_pdf(item), original_pdf)
        response = self.api.get(reverse("tutor-personnel-forms"))
        self.assertEqual(response.data["results"][0]["status"], "Leave approved")
        self.assertEqual(response.data["results"][0]["review_notes"], item.review_notes)
        self.assertIsNotNone(response.data["results"][0]["reviewed_at"])

    def test_staff_tutor_cannot_review_or_download_other_tutors_forms(self):
        item, _ = self.submit()
        other = get_user_model().objects.create_user(
            username="personnel-staff-tutor", email="staff-tutor@example.test", is_staff=True
        )
        other.groups.add(self.group)
        other.user_permissions.add(
            *Permission.objects.filter(codename__in=["view_tutorpersonnelform", "change_tutorpersonnelform"])
        )
        model_admin = TutorPersonnelFormAdmin(TutorPersonnelForm, admin.site)
        request = RequestFactory().get("/admin/")
        request.user = other
        self.assertFalse(model_admin.has_change_permission(request, item))
        self.assertFalse(model_admin.get_queryset(request).exists())
        self.client.force_login(other)
        response = self.client.get(
            reverse("admin:content_tutorpersonnelform_pdf", args=[item.pk]), HTTP_X_FORWARDED_PROTO="https"
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request, item))

    def test_invalid_review_status_cannot_approve_resignation_as_leave(self):
        item, _ = self.submit()
        item.status = "acknowledged"
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_history_is_paginated_and_bounded(self):
        for index in range(11):
            self.submit(key=f"history-test-{index:03}")
        first = self.api.get(reverse("tutor-personnel-forms"))
        self.assertEqual(len(first.data["results"]), 10)
        self.assertTrue(first.data["has_more"])
        second = self.api.get(reverse("tutor-personnel-forms"), {"page": "2"})
        self.assertEqual(len(second.data["results"]), 1)
        self.assertFalse(second.data["has_more"])


@override_settings(
    TUTOR_PERSONNEL_FORMS_ENABLED=True,
    TUTOR_PERSONNEL_ADMIN_EMAIL="",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class TutorPersonnelWorkflowTests(PersonnelFixtures, TestCase):
    """Exercise real API/Admin HTTP handlers together; storage and SMTP remain isolated."""

    def journey(self, *, kind, status, expected_status):
        self.api.force_authenticate(user=None)
        self.api.credentials(HTTP_AUTHORIZATION="Bearer synthetic-verified-tutor")
        identity = {
            "id": str(uuid.uuid4()),
            "email": self.tutor.email,
            "email_confirmed_at": "2026-01-01T00:00:00Z",
        }
        values = {**self.values, "idempotency_key": f"workflow-{kind}-{status}"}
        if kind == "resignation":
            for field in ("leave_type", "start_date", "end_date"):
                values.pop(field)
            values.update(kind=kind, last_teaching_day=self.today + timedelta(days=30))
        reviewer = get_user_model().objects.create_superuser(
            username="workflow-admin", email="reviewer@example.test", password="synthetic-isolated-only"
        )
        admin_client = Client(enforce_csrf_checks=True)
        admin_client.force_login(reviewer)
        with patch("content.tutor_views.SupabaseStudentAuthentication._validate_token", return_value=identity):
            submitted = self.api.post(reverse("tutor-personnel-forms"), values, format="json")
            self.assertEqual(submitted.status_code, 201, submitted.data)
            item = TutorPersonnelForm.objects.get(pk=submitted.data["id"])
            self.assertEqual(item.tutor, self.tutor)
            self.assertEqual(item.delivery_status, "queued")
            self.assertEqual(len(mail.outbox), 0, "Submitting the form must not send SMTP inside the request.")
            original_pdf = self.api.get(reverse("tutor-personnel-pdf", args=[item.pk]))
            self.assertEqual(original_pdf.status_code, 200)
            self.assertEqual(original_pdf["Content-Type"], "application/pdf")

            change_url = reverse("admin:content_tutorpersonnelform_change", args=[item.pk])
            review_page = admin_client.get(change_url, secure=True)
            self.assertEqual(review_page.status_code, 200)
            self.assertContains(review_page, str(item.pk))
            self.assertContains(review_page, "Download private PDF")
            # A genuine Admin form POST must enforce CSRF, validation and permissions.
            rejected = admin_client.post(change_url, {"status": status, "review_notes": "Missing CSRF."}, secure=True)
            self.assertEqual(rejected.status_code, 403)
            notes = f"Admin reviewed {kind} and confirmed the handover plan."
            reviewed = admin_client.post(
                change_url,
                {
                    "status": status,
                    "review_notes": notes,
                    "_save": "Save",
                    "csrfmiddlewaretoken": admin_client.cookies["csrftoken"].value,
                },
                secure=True,
                HTTP_REFERER=f"https://testserver{change_url}",
            )
            self.assertEqual(reviewed.status_code, 302, getattr(reviewed, "context", None))
            item.refresh_from_db()
            self.assertEqual(item.status, status)
            self.assertEqual(item.reviewed_by_id, reviewer.pk)
            self.assertIsNotNone(item.reviewed_at)
            self.assertEqual(item.delivery_status, "queued", "Reviewing a form must not overwrite its outbox.")

            dashboard = self.api.get(reverse("tutor-personnel-forms"))
            self.assertEqual(dashboard.status_code, 200)
            saved = dashboard.data["results"][0]
            self.assertEqual(saved["id"], str(item.pk))
            self.assertEqual(saved["status"], expected_status)
            self.assertEqual(saved["review_notes"], notes)
            admin_pdf = admin_client.get(reverse("admin:content_tutorpersonnelform_pdf", args=[item.pk]), secure=True)
            tutor_pdf = self.api.get(reverse("tutor-personnel-pdf", args=[item.pk]))
            self.assertEqual(admin_pdf.status_code, 200)
            self.assertEqual(admin_pdf.content, original_pdf.content)
            self.assertEqual(tutor_pdf.content, original_pdf.content)
            self.assertIn("no-store", admin_pdf["Cache-Control"])

            self.assertEqual(deliver_tutor_personnel_forms(), 1)
            self.assertEqual(deliver_tutor_personnel_forms(), 0)
            item.refresh_from_db()
            self.assertEqual(item.delivery_status, "sent")
            self.assertEqual(len(mail.outbox), 1)
            message = mail.outbox[0]
            self.assertEqual(message.to, ["admin@example.test"])
            self.assertEqual(message.attachments[0].content, original_pdf.content)
            self.assertIn("Official academy communication", message.alternatives[0].content)
            for field in ("reason", "handover", "signature_name", "contact_phone"):
                self.assertIn(str(values[field]), message.body)
            self.assertIn(str(item.pk), message.body)

            retry = self.api.post(reverse("tutor-personnel-forms"), values, format="json")
            self.assertEqual(retry.status_code, 200)
            self.assertEqual(retry.data["id"], str(item.pk))
            self.assertEqual(retry.data["status"], expected_status)
            self.assertEqual(TutorPersonnelForm.objects.count(), 1)
            self.assertEqual(deliver_tutor_personnel_forms(), 0)
            self.assertEqual(len(mail.outbox), 1)
            self.tutor.refresh_from_db()
            self.assertTrue(self.tutor.is_active)
            self.assertTrue(self.tutor.groups.filter(name="Tutors").exists())

    def test_leave_submission_admin_approval_dashboard_pdf_and_email(self):
        self.journey(kind="leave", status="approved", expected_status="Leave approved")

    def test_leave_submission_admin_decline_dashboard_pdf_and_email(self):
        self.journey(kind="leave", status="declined", expected_status="Leave declined")

    def test_resignation_submission_admin_acknowledgement_dashboard_pdf_and_email(self):
        self.journey(kind="resignation", status="acknowledged", expected_status="Resignation acknowledged")


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row locks / RLS required")
@override_settings(TUTOR_PERSONNEL_ADMIN_EMAIL="", EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class TutorPersonnelPostgresTests(PersonnelFixtures, TransactionTestCase):
    def test_overlapping_workers_claim_one_email_and_rls_enabled(self):
        item, _ = self.submit()
        barrier = Barrier(2)

        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return deliver_form(item.pk)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: worker(), range(2)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(len(mail.outbox), 1)
        with connection.cursor() as cursor:
            cursor.execute("SELECT relrowsecurity FROM pg_class WHERE oid = 'content_tutorpersonnelform'::regclass")
            self.assertTrue(cursor.fetchone()[0])
            cursor.execute("SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated')")
            for (role,) in cursor.fetchall():
                cursor.execute("SELECT has_table_privilege(%s, 'content_tutorpersonnelform', 'SELECT')", [role])
                self.assertFalse(cursor.fetchone()[0])
