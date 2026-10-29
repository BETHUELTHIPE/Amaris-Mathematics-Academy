import io
import uuid
from datetime import timedelta
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core import mail
from django.core.cache import cache
from django.core.files.storage import storages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from content.authentication import SupabaseStudentAuthentication
from content.models import StudentRecord, TutorApplication, TutorApplicationDocument
from content.services.tutor_applications import deliver_application_acknowledgement

STORAGES = {
    "tutor_qualifications": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=STORAGES, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class TutorApplicationJourneyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.api = APIClient()
        self.user_id = uuid.uuid4()
        self.endpoint = reverse("tutor-applications")
        self.payload = {"id": str(self.user_id), "email": "applicant@example.test", "email_confirmed_at": "2026-10-01"}
        self.patch = patch.object(SupabaseStudentAuthentication, "_validate_token", return_value=self.payload)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.queue = patch("content.tasks.deliver_tutor_application_acknowledgements.delay")
        self.enqueue = self.queue.start()
        self.addCleanup(self.queue.stop)
        self.api.credentials(HTTP_AUTHORIZATION="Bearer synthetic-test-token")

    def form(self, **changes):
        form = {
            "full_name": "Synthetic Applicant",
            "phone": "+27 71 234 5678",
            "location": "Pretoria, South Africa",
            "qualification": "BSc Mathematics",
            "institution": "Synthetic University",
            "subjects": "Mathematics",
            "programmes": ["caps", "university"],
            "levels": "Grade 12 and first year",
            "experience_years": "3",
            "teaching_experience": "Three years of mathematics tutoring.",
            "availability": "Weekday evenings SAST, Zoom and internet available.",
            "motivation": "I enjoy helping learners understand mathematics clearly.",
            "consent": "true",
            "documents": [
                SimpleUploadedFile("qualification.pdf", b"%PDF-1.7\nsynthetic test\n%%EOF", "application/pdf")
            ],
        }
        form.update(changes)
        return form

    def submit(self, **changes):
        return self.api.post(self.endpoint, self.form(**changes), format="multipart", secure=True)

    def test_complete_authenticated_application_owner_download_and_email(self):
        self.assertIsNone(self.api.get(self.endpoint, secure=True).data["application"])
        result = self.submit(email="attacker@example.test", status="shortlisted", acknowledgement_sent_at="2026-01-01")
        self.assertEqual(result.status_code, 201, result.data)
        application = TutorApplication.objects.get()
        self.assertEqual(application.email, "applicant@example.test")
        self.assertEqual(application.supabase_user_id, self.user_id)
        self.assertEqual(application.status, "submitted")
        self.assertIsNotNone(application.acknowledgement_sent_at)
        self.assertEqual(StudentRecord.objects.count(), 0)
        self.assertEqual(get_user_model().objects.count(), 0)
        self.assertEqual(Group.objects.count(), 0)
        self.enqueue.assert_called_once()
        self.assertNotIn("storage_path", str(result.data))
        self.assertNotIn("review_notes", str(result.data))
        document = TutorApplicationDocument.objects.get()
        self.assertNotIn("qualification.pdf", document.storage_path)
        download = self.api.get(reverse("tutor-application-document", args=[document.pk]), secure=True)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download["Cache-Control"], "private, no-store")
        self.assertEqual(download["Content-Type"], "application/octet-stream")
        self.assertIn(b"%PDF", b"".join(download.streaming_content))
        self.assertEqual(deliver_application_acknowledgement(), 0)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [application.email])
        self.assertIn(application.reference, mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].attachments, [])
        self.assertEqual(deliver_application_acknowledgement(), 0)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIsNotNone(self.api.get(self.endpoint, secure=True).data["application"]["acknowledgement_sent_at"])

    def test_anonymous_unverified_and_other_user_cannot_access_private_files(self):
        self.api.credentials()
        self.assertEqual(self.submit().status_code, 401)
        self.api.credentials(HTTP_AUTHORIZATION="Bearer synthetic-test-token")
        self.payload["email_confirmed_at"] = None
        self.assertEqual(self.submit().status_code, 401)
        self.payload["email_confirmed_at"] = "2026-10-01"
        self.assertEqual(self.submit().status_code, 201)
        document = TutorApplicationDocument.objects.get()
        self.payload["id"] = str(uuid.uuid4())
        self.assertIsNone(self.api.get(self.endpoint, secure=True).data["application"])
        self.assertEqual(
            self.api.get(reverse("tutor-application-document", args=[document.pk]), secure=True).status_code, 404
        )

    @staticmethod
    def six_documents():
        return {
            name: SimpleUploadedFile(
                name + ".pdf", b"%PDF-1.7\\nsynthetic " + name.encode() + b"\\n%%EOF", "application/pdf"
            )
            for name in (
                "document_id",
                "document_cv",
                "document_matric",
                "document_academic",
                "document_tertiary",
                "document_other",
            )
        }

    @override_settings(TUTOR_REQUIRE_SIX_DOCUMENTS=True)
    def test_six_categorized_documents_are_required_and_private(self):
        for missing in self.six_documents():
            with self.subTest(missing=missing):
                files = self.six_documents()
                del files[missing]
                response = self.submit(documents=[], **files)
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn(missing, response.data)
        self.assertEqual(TutorApplication.objects.count(), 0)
        response = self.submit(documents=[], **self.six_documents())
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            set(TutorApplicationDocument.objects.values_list("category", flat=True)),
            {"id", "cv", "matric", "academic", "tertiary", "other"},
        )
        self.assertEqual(
            {d["category"] for d in response.data["application"]["documents"]},
            {"id", "cv", "matric", "academic", "tertiary", "other"},
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].attachments, [])
        self.assertTrue(all("storage_path" not in str(d) for d in response.data["application"]["documents"]))
        self.enqueue.assert_called_once()

    @override_settings(TUTOR_REQUIRE_SIX_DOCUMENTS=True)
    def test_legacy_or_oversized_six_document_form_is_rejected(self):
        self.assertEqual(self.submit().status_code, 400)
        extra = self.six_documents()
        extra["documents"] = [SimpleUploadedFile("extra.pdf", b"%PDF-test", "application/pdf")]
        response = self.submit(**extra)
        self.assertEqual(response.status_code, 400, response.data)
        oversized = self.six_documents()
        oversized["document_id"] = SimpleUploadedFile("id.pdf", b"%PDF-" + b"x" * (5 * 1024 * 1024), "application/pdf")
        response = self.submit(documents=[], **oversized)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("document_id", response.data)
        self.assertEqual(TutorApplicationDocument.objects.count(), 0)

    def test_invalid_forms_and_uploads_create_no_application(self):
        cases = [
            {"consent": "false"},
            {"documents": []},
            {"programmes": []},
            {"programmes": ["invalid"]},
            {"motivation": "x"},
            {"experience_years": "-1"},
            {"documents": [SimpleUploadedFile("bad.pdf", b"<script>alert(1)</script>", "application/pdf")]},
            {"documents": [SimpleUploadedFile("bad.png", b"not an image", "image/png")]},
            {"documents": [SimpleUploadedFile("program.exe", b"binary", "application/octet-stream")]},
            {"documents": [SimpleUploadedFile("big.pdf", b"%PDF-" + b"x" * (5 * 1024 * 1024), "application/pdf")]},
        ]
        for case in cases:
            with self.subTest(case=list(case)):
                response = self.submit(**case)
                self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(TutorApplication.objects.count(), 0)
        self.assertEqual(TutorApplicationDocument.objects.count(), 0)
        self.enqueue.assert_not_called()

    def test_png_qualification_accepted_and_duplicate_submission_idempotent(self):
        data = io.BytesIO()
        Image.new("RGB", (2, 2)).save(data, "PNG")
        self.assertEqual(
            self.submit(documents=[SimpleUploadedFile("scan.png", data.getvalue(), "image/png")]).status_code, 201
        )
        self.assertEqual(self.submit(full_name="Overwrite attempt").status_code, 200)
        self.assertEqual(TutorApplication.objects.count(), 1)
        self.assertEqual(TutorApplication.objects.get().full_name, "Synthetic Applicant")
        self.assertEqual(TutorApplicationDocument.objects.count(), 1)
        self.enqueue.assert_called_once()

    @override_settings(TUTOR_REQUIRE_SIX_DOCUMENTS=True)
    def test_six_uploads_complete_before_any_database_savepoint(self):
        # Django TestCase owns an outer rollback transaction. Assert that the
        # upload path never opens a further atomic block around slow S3 calls.
        storage = storages["tutor_qualifications"]
        original_save = storage.save
        initial_savepoints = len(connection.savepoint_ids)
        observed = []

        def observe_save(path, content, **kwargs):
            observed.append(len(connection.savepoint_ids))
            self.assertEqual(len(connection.savepoint_ids), initial_savepoints)
            return original_save(path, content, **kwargs)

        with patch.object(storage, "save", side_effect=observe_save):
            response = self.submit(documents=[], **self.six_documents())
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(observed, [initial_savepoints] * 6)
        self.assertEqual(TutorApplication.objects.count(), 1)
        self.assertEqual(TutorApplicationDocument.objects.count(), 6)

    def test_upload_failure_rolls_back_record_and_cleans_previously_saved_document(self):
        storage = storages["tutor_qualifications"]
        save = storage.save
        calls = []

        def fail_second(path, content, **kwargs):
            calls.append(path)
            if len(calls) == 2:
                raise OSError("synthetic storage outage")
            return save(path, content, **kwargs)

        with patch.object(storage, "save", side_effect=fail_second):
            response = self.submit(documents=[self.form()["documents"][0], self.form()["documents"][0]])
        self.assertEqual(response.status_code, 503)
        self.assertEqual(TutorApplication.objects.count(), 0)
        self.assertFalse(storage.exists(calls[0]))
        self.enqueue.assert_not_called()

    def test_broker_and_mail_failure_leave_recoverable_application(self):
        self.enqueue.side_effect = OSError("synthetic broker outage")
        with patch("django.core.mail.EmailMultiAlternatives.send", side_effect=OSError("synthetic SMTP outage")):
            self.assertEqual(self.submit().status_code, 201)
            self.assertEqual(deliver_application_acknowledgement(), 0)
        application = TutorApplication.objects.get()
        self.assertIsNone(application.acknowledgement_sent_at)
        self.assertEqual(application.acknowledgement_attempts, 1)
        self.assertEqual(application.acknowledgement_error, "OSError")
        self.assertGreater(application.acknowledgement_next_attempt_at, timezone.now())
        TutorApplication.objects.update(acknowledgement_next_attempt_at=timezone.now() - timedelta(seconds=1))
        retried = self.api.post(reverse("tutor-application-acknowledgement"), secure=True)
        self.assertEqual(retried.status_code, 200)
        application.refresh_from_db()
        self.assertIsNotNone(application.acknowledgement_sent_at)
        self.assertEqual(len(mail.outbox), 1)

    def test_admin_documents_need_recruitment_permission(self):
        self.assertEqual(self.submit().status_code, 201)
        document = TutorApplicationDocument.objects.get()
        staff = get_user_model().objects.create_user(username="staff", is_staff=True)
        self.client.force_login(staff)
        url = reverse("admin:tutor-application-document", args=[document.pk])
        self.assertEqual(self.client.get(url, secure=True).status_code, 403)
        staff.user_permissions.add(Permission.objects.get(codename="view_tutorapplication"))
        self.assertEqual(self.client.get(url, secure=True).status_code, 200)

    @skipUnless(connection.vendor == "postgresql", "PostgreSQL RLS assertion")
    def test_recruitment_tables_deny_data_api_roles(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relname, relrowsecurity FROM pg_class WHERE relname IN (%s, %s)",
                ["content_tutorapplication", "content_tutorapplicationdocument"],
            )
            self.assertEqual(len(rows := cursor.fetchall()), 2)
            self.assertTrue(all(enabled for _table, enabled in rows))
            cursor.execute("SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')")
            roles = [role for (role,) in cursor.fetchall()]
            for role in roles:
                for table, _enabled in rows:
                    cursor.execute("SELECT has_table_privilege(%s, %s, 'SELECT,INSERT,UPDATE,DELETE')", [role, table])
                    self.assertFalse(cursor.fetchone()[0])
