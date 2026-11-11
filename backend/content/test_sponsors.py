import csv
import io
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest import skipUnless
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .authentication import SupabaseStudentAuthentication
from .models import Course, CourseCategory, Enrollment, StudentRecord
from .sponsor_models import SponsorAccount, SponsorAllocation, SponsorContribution


class SponsorDashboardTests(TestCase):
    def setUp(self):
        self.sponsor = SponsorAccount.objects.create(
            supabase_user_id=uuid.uuid4(),
            name="Sponsor One",
            organisation="Example Foundation",
            is_active=True,
            annual_target="20000.00",
        )
        self.other = SponsorAccount.objects.create(supabase_user_id=uuid.uuid4(), name="Other", is_active=True)
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION="Bearer synthetic-sponsor-token")
        self.payload = {"id": str(self.sponsor.supabase_user_id), "email_confirmed_at": "2026-10-01"}
        self.auth_patch = patch.object(SupabaseStudentAuthentication, "_validate_token", return_value=self.payload)
        self.auth_patch.start()
        self.addCleanup(self.auth_patch.stop)
        self.url = reverse("sponsor-dashboard")
        self.student = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(),
            email="private@example.test",
            first_name="Private",
            last_name="Student",
            mobile="0712345678",
        )
        category = CourseCategory.objects.create(name="Test", slug="test")
        course = Course.objects.create(
            category=category,
            title="Test",
            slug="test",
            price="100.00",
            short_description="Test",
            description="Test",
            curriculum="CAPS",
            academic_level="12",
        )
        self.enrollment = Enrollment.objects.create(
            student=self.student,
            course=course,
            progress_percent=62,
            status="active",
            progress_updated_at=timezone.now(),
        )

    def contribution(self, sponsor=None, amount="1000.00", status="received", **kwargs):
        return SponsorContribution.objects.create(
            sponsor=sponsor or self.sponsor,
            reference=str(uuid.uuid4()),
            amount=amount,
            status=status,
            received_at=timezone.now() if status == "received" else None,
            **kwargs,
        )

    def allocation(self, sponsor=None, **kwargs):
        return SponsorAllocation.objects.create(
            sponsor=sponsor or self.sponsor,
            student=self.student,
            learner_label="Learner A01",
            programme="caps",
            level="Grade 12",
            amount="300.00",
            starts_on=timezone.localdate(),
            **kwargs,
        )

    def test_requires_verified_approved_sponsor_uuid_not_metadata_or_email(self):
        self.api.credentials()
        self.assertEqual(self.api.get(self.url, secure=True).status_code, 401)
        self.api.credentials(HTTP_AUTHORIZATION="Bearer synthetic-sponsor-token")
        self.payload["email_confirmed_at"] = None
        self.assertEqual(self.api.get(self.url, secure=True).status_code, 401)
        self.payload["email_confirmed_at"] = "2026-10-01"
        self.payload.update(id=str(uuid.uuid4()), email="sponsor-one@example.test", user_metadata={"role": "sponsor"})
        self.assertEqual(self.api.get(self.url, secure=True).status_code, 403)
        self.payload["id"] = "invalid-uuid"
        self.assertEqual(self.api.get(self.url, secure=True).status_code, 401)
        self.payload["id"] = str(self.sponsor.supabase_user_id)
        self.sponsor.is_active = False
        self.sponsor.save()
        self.assertEqual(self.api.get(self.url, secure=True).status_code, 403)

    def test_totals_and_data_are_scoped_to_sponsor_with_distinct_student_counts(self):
        self.contribution(amount="1000.10")
        self.contribution(amount="500.00", status="pledged")
        self.contribution(amount="200.00", status="refunded")
        self.contribution(sponsor=self.other, amount="90000.00")
        self.allocation(status="active")
        self.allocation(status="completed")
        self.allocation(status="planned")
        self.allocation(status="cancelled")
        self.allocation(sponsor=self.other, status="active")
        response = self.api.get(self.url, {"sponsor_id": str(self.other.id)}, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"]["received"], "1000.10")
        self.assertEqual(response.data["summary"]["pledged"], "500.00")
        self.assertEqual(response.data["summary"]["allocated"], "600.00")
        self.assertEqual(response.data["summary"]["balance"], "400.10")
        self.assertEqual(response.data["summary"]["students_supported"], 1)
        self.assertEqual(response.data["summary"]["active_students"], 1)
        self.assertEqual(len(response.data["learners"]), 4)
        self.assertEqual(len(response.data["contributions"]), 3)
        self.assertEqual(len(response.data["monthly_contributions"]), 12)
        self.assertEqual(
            sum(Decimal(row["amount"]) for row in response.data["monthly_contributions"]), Decimal("1000.10")
        )
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertIn("Authorization", response["Vary"])

    def test_progress_requires_explicit_consent_and_no_student_pii_is_returned(self):
        allocation = self.allocation(status="active", enrollment=self.enrollment)
        response = self.api.get(self.url, secure=True)
        record = response.data["learners"][0]
        self.assertIsNone(record["progress_percent"])
        self.assertIsNone(record["progress_updated_at"])
        body = response.content.decode()
        for private_value in (
            self.student.email,
            self.student.first_name,
            self.student.last_name,
            self.student.mobile,
            str(self.student.supabase_user_id),
        ):
            self.assertNotIn(private_value, body)
        allocation.share_progress, allocation.progress_consented_at = True, timezone.now()
        allocation.save()
        self.assertEqual(self.api.get(self.url, secure=True).data["learners"][0]["progress_percent"], 62)
        other = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(), email="other@example.test", first_name="Other", last_name="Private"
        )
        SponsorAllocation.objects.filter(pk=allocation.pk).update(student=other)
        self.assertIsNone(self.api.get(self.url, secure=True).data["learners"][0]["progress_percent"])

    def test_year_filter_and_all_time_summary_are_distinct(self):
        prior_year = timezone.localdate().year - 1
        payment = self.contribution()
        SponsorContribution.objects.filter(pk=payment.pk).update(received_at=timezone.now().replace(year=prior_year))
        response = self.api.get(self.url, {"year": prior_year}, secure=True)
        self.assertEqual(response.data["year"], prior_year)
        self.assertEqual(response.data["summary"]["received"], "1000.00")
        self.assertEqual(response.data["summary"]["current_year_received"], "0.00")
        self.assertEqual(len(response.data["contributions"]), 1)
        self.assertEqual(self.api.get(self.url, secure=True).data["contributions"], [])

    def test_invalid_year_and_page_rejected_and_endpoints_are_read_only(self):
        for query in ({"year": "invalid"}, {"year": "2019"}, {"year": "9999"}, {"page": "0"}, {"page": "bad"}):
            self.assertEqual(self.api.get(self.url, query, secure=True).status_code, 400)
        self.assertEqual(self.api.post(self.url, {}, secure=True).status_code, 405)
        self.assertEqual(self.api.post(reverse("sponsor-statement"), {}, secure=True).status_code, 405)

    def test_pagination_does_not_truncate_totals_or_statement(self):
        for _ in range(22):
            self.contribution()
        response = self.api.get(self.url, {"page": "2"}, secure=True)
        self.assertEqual(len(response.data["contributions"]), 2)
        self.assertEqual(response.data["contributions_total"], 22)
        self.assertEqual(response.data["summary"]["received"], "22000.00")
        response = self.api.get(reverse("sponsor-statement"), secure=True)
        records = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(len(records), 23)
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_statement_ownership_and_spreadsheet_formula_safety(self):
        payment = self.contribution(description="  =IMPORTDATA(123)")
        SponsorContribution.objects.filter(pk=payment.pk).update(reference="@unsafe")
        other = self.contribution(sponsor=self.other, description="Other sponsor private reference")
        response = self.api.get(reverse("sponsor-statement"), {"sponsor_id": str(self.other.id)}, secure=True)
        body = response.content.decode("utf-8-sig")
        self.assertNotIn(other.reference, body)
        rows = list(csv.reader(io.StringIO(body)))
        self.assertEqual(rows[1][0], "'@unsafe")
        self.assertTrue(rows[1][2].startswith("'"))
        self.assertEqual(rows[1][-1], "ZAR")
        self.assertIn("attachment", response["Content-Disposition"])

    def test_empty_account_returns_real_empty_state_and_zero_totals(self):
        response = self.api.get(self.url, secure=True)
        self.assertEqual(response.data["summary"]["received"], "0.00")
        self.assertEqual(response.data["learners"], [])
        self.assertEqual(response.data["contributions"], [])

    def test_model_validation_rejects_mismatched_enrollment_and_missing_consent(self):
        allocation = self.allocation(enrollment=self.enrollment)
        allocation.share_progress = True
        with self.assertRaises(ValidationError):
            allocation.full_clean()
        allocation.progress_consented_at = timezone.now()
        allocation.ends_on = allocation.starts_on - timedelta(days=1)
        with self.assertRaises(ValidationError):
            allocation.full_clean()
        allocation.ends_on = None
        other = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(), email="mismatch@example.test", first_name="Other", last_name="Student"
        )
        allocation.student = other
        with self.assertRaises(ValidationError):
            allocation.full_clean()

    def test_database_rejects_invalid_contribution_and_missing_consent(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.contribution(amount="0")
        with self.assertRaises(IntegrityError), transaction.atomic():
            SponsorContribution.objects.create(
                sponsor=self.sponsor, reference="missing-date", amount="100.00", status="received"
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.allocation(share_progress=True)

    @skipUnless(connection.vendor == "postgresql", "PostgreSQL RLS assertion")
    def test_new_tables_are_private_and_deny_data_api_roles(self):
        tables = ("content_sponsoraccount", "content_sponsorcontribution", "content_sponsorallocation")
        with connection.cursor() as cursor:
            cursor.execute("SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')")
            roles = cursor.fetchall()
            for table in tables:
                cursor.execute("SELECT relrowsecurity FROM pg_class WHERE oid=%s::regclass", [table])
                self.assertTrue(cursor.fetchone()[0])
                for (role,) in roles:
                    cursor.execute("SELECT has_table_privilege(%s, %s, 'SELECT,INSERT,UPDATE,DELETE')", [role, table])
                    self.assertFalse(cursor.fetchone()[0])
