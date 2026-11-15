from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.files.storage import InMemoryStorage
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader
from rest_framework.test import APIClient

from content.models import SiteSettings
from content.services.tutor_contracts import archived_contract_pdf, deliver_contract, submit_contract
from content.services.tutor_video_uploads import UploadConflict
from content.tutor_contract_admin import TutorEmploymentContractAdmin
from content.tutor_contract_models import TutorEmploymentContract
from content.tutor_finance_models import TutorContract


@override_settings(
    TUTOR_PERSONNEL_FORMS_ENABLED=True,
    TUTOR_PERSONNEL_ADMIN_EMAIL="",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class TutorEmploymentContractTests(TestCase):
    def setUp(self):
        self.tutor = get_user_model().objects.create_user(
            username="contract-tutor", email="tutor@example.test", first_name="Tutor", last_name="Example"
        )
        self.tutor.groups.add(Group.objects.get_or_create(name="Tutors")[0])
        SiteSettings.objects.create(email="admin@example.test")
        TutorContract.objects.create(
            tutor=self.tutor,
            service="live_class",
            tutor_percent="60.00",
            contract_reference="ADMIN-RATE-001",
        )
        self.storage = InMemoryStorage()
        for name in ("employee_pdf", "executed_pdf"):
            field_patch = patch.object(TutorEmploymentContract._meta.get_field(name), "storage", self.storage)
            field_patch.start()
            self.addCleanup(field_patch.stop)
        self.values = {
            "residential_address": "10 Example Street, Johannesburg, Gauteng",
            "contact_phone": "+27 71 234 5678",
            "preferred_start_date": timezone.localdate() + timedelta(days=7),
            "ordinary_work_days": ["Monday", "Wednesday", "Saturday"],
            "maximum_weekly_hours": 20,
            "signature_name": "Tutor Example",
            "accept_employment_terms": True,
            "accept_privacy_notice": True,
            "accept_safeguarding_duties": True,
            "consent_electronic_signature": True,
        }
        self.api = APIClient()
        self.api.force_authenticate(user=self.tutor)

    def test_save_first_private_pdf_then_exact_admin_attachment(self):
        item, created = submit_contract(tutor=self.tutor, key="employment-contract-001", values=self.values)
        self.assertTrue(created)
        self.assertEqual(item.status, "submitted")
        self.assertEqual(str(item.statutory_hourly_floor), "30.23")
        self.assertTrue(item.employee_pdf.name.startswith(f"tutor-contracts/{self.tutor.pk}/{item.pk}/"))
        document = archived_contract_pdf(item)
        text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(document)).pages)
        for value in ["Tutor contract of employment", "R30.23", "PAYE", "UIF", "POPIA", "ADMIN-RATE-001"]:
            self.assertIn(value, text)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(deliver_contract(item.pk), 1)
        self.assertEqual(deliver_contract(item.pk), 0)
        self.assertEqual(mail.outbox[0].to, ["admin@example.test"])
        self.assertEqual(mail.outbox[0].attachments[0].content, document)
        self.assertEqual(mail.outbox[0].extra_headers["Message-ID"], f"<tutor-employment-{item.pk}@amaris.academy>")

    def test_retry_is_idempotent_and_changed_payload_conflicts(self):
        first, _ = submit_contract(tutor=self.tutor, key="employment-contract-002", values=self.values)
        second, created = submit_contract(tutor=self.tutor, key="employment-contract-002", values=self.values)
        self.assertFalse(created)
        self.assertEqual(first.pk, second.pk)
        with self.assertRaises(UploadConflict):
            submit_contract(
                tutor=self.tutor,
                key="employment-contract-002",
                values={**self.values, "maximum_weekly_hours": 21},
            )

    def test_api_ignores_client_owned_terms_and_other_tutor_cannot_download(self):
        response = self.api.post(
            reverse("tutor-employment-contracts"),
            {
                **self.values,
                "idempotency_key": "employment-contract-api",
                "tutor_percent": "100.00",
                "recipient": "attacker@example.test",
                "status": "accepted",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        item = TutorEmploymentContract.objects.get()
        self.assertEqual(item.service_terms[0]["tutor_percent"], "60.00")
        self.assertEqual(item.recipient, "admin@example.test")
        self.assertEqual(item.status, "submitted")
        own = self.api.get(reverse("tutor-employment-contract-pdf", args=[item.pk]))
        self.assertEqual(own.status_code, 200)
        other = get_user_model().objects.create_user(username="other", email="other@example.test")
        other.groups.add(Group.objects.get(name="Tutors"))
        self.api.force_authenticate(user=other)
        self.assertEqual(self.api.get(reverse("tutor-employment-contract-pdf", args=[item.pk])).status_code, 404)

    def test_superuser_countersign_creates_executed_copy_and_final_decision_is_immutable(self):
        item, _ = submit_contract(tutor=self.tutor, key="employment-contract-003", values=self.values)
        original = archived_contract_pdf(item)
        reviewer = get_user_model().objects.create_superuser(
            username="contract-admin", email="reviewer@example.test", password="synthetic-only"
        )
        model_admin = TutorEmploymentContractAdmin(TutorEmploymentContract, admin.site)
        request = RequestFactory().post("/admin/")
        request.user = reviewer
        item.status = "accepted"
        item.review_notes = "Identity and remuneration schedule verified."
        item.employer_signature_name = "Authorised Super User"
        item.effective_date = timezone.localdate() + timedelta(days=7)
        model_admin.save_model(request, item, None, True)
        item.refresh_from_db()
        self.assertEqual(item.status, "accepted")
        self.assertTrue(item.executed_pdf)
        executed = archived_contract_pdf(item)
        self.assertNotEqual(original, executed)
        text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(executed)).pages)
        self.assertIn("EXECUTED COPY", text)
        self.assertIn("Authorised Super User", text)
        with self.assertRaises(Exception):
            item.status = "declined"
            model_admin.save_model(request, item, None, True)

    def test_no_live_class_remuneration_blocks_signing(self):
        TutorContract.objects.all().delete()
        response = self.api.get(reverse("tutor-employment-contracts"))
        self.assertFalse(response.data["offer"]["available"])
        post = self.api.post(
            reverse("tutor-employment-contracts"),
            {**self.values, "idempotency_key": "employment-no-rate"},
            format="json",
        )
        self.assertEqual(post.status_code, 409)
        self.assertEqual(TutorEmploymentContract.objects.count(), 0)

    def test_private_storage_failure_never_creates_outbox_record(self):
        with patch.object(self.storage, "save", side_effect=OSError("synthetic unavailable")):
            response = self.api.post(
                reverse("tutor-employment-contracts"),
                {**self.values, "idempotency_key": "employment-storage-fail"},
                format="json",
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(TutorEmploymentContract.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)
