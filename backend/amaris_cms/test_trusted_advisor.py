import json
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from amaris_cms.advisor_evidence import BACKUP_WORKFLOW, frontend_probe, latest_workflow_run
from amaris_cms.trusted_advisor import (
    AdvisorReport,
    Finding,
    Status,
    backup_finding,
    collect_advisor_report,
    operations_findings,
    release_finding,
    storage_finding,
    table_access_finding,
)
from content.models import PaymentReconciliationRun

TEST_STORAGES = {
    **settings.STORAGES,
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=TEST_STORAGES)
class AdvisorAdminTests(TestCase):
    staff: User
    superuser: User

    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_user(username="advisor-staff", is_staff=True)
        cls.superuser = get_user_model().objects.create_superuser(username="advisor-superuser")

    @patch("amaris_cms.monitoring_admin.collect_advisor_report")
    def test_guest_and_staff_are_denied_before_the_advisor_runs(self, collect):
        url = reverse("admin:amaris_trusted_advisor")
        guest = self.client.get(url, secure=True)
        self.assertRedirects(guest, f"/admin/login/?next={url}", fetch_redirect_response=False)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(url, secure=True).status_code, 403)
        self.assertNotContains(self.client.get(reverse("admin:index"), secure=True), "Open Trusted Advisor")
        collect.assert_not_called()

    @patch("amaris_cms.monitoring_admin.collect_advisor_report")
    def test_superuser_can_read_report_and_reports_are_never_cached(self, collect):
        url = reverse("admin:amaris_trusted_advisor")
        collect.return_value = AdvisorReport(
            timezone.now(),
            [Finding("Security", "Test control", Status.ACTION, "<script>alert(1)</script>")],
            {"action": 1, "verify": 0, "passed": 0},
        )
        self.client.force_login(self.superuser)
        self.assertContains(self.client.get(reverse("admin:index"), secure=True), "Open Trusted Advisor")
        result = self.client.get(url, secure=True)
        self.assertContains(result, "Test control")
        self.assertContains(result, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertIn("no-store", result.headers["Cache-Control"])
        self.assertEqual(self.client.post(url, secure=True).status_code, 405)
        collect.assert_called_once_with()

    def test_reconciliation_reflects_observed_outcomes(self):
        now = timezone.now()
        reports = {finding.title: finding for finding in operations_findings(True, now)}
        self.assertEqual(reports["Payment reconciliation"].status, Status.VERIFY)
        PaymentReconciliationRun.objects.create(
            status=PaymentReconciliationRun.Status.SUCCEEDED, started_at=now, completed_at=now
        )
        reports = {finding.title: finding for finding in operations_findings(True, now)}
        self.assertEqual(reports["Payment reconciliation"].status, Status.PASS)
        latest = PaymentReconciliationRun.objects.create(
            status=PaymentReconciliationRun.Status.SUCCEEDED, started_at=now + timedelta(seconds=1), unresolved_count=2
        )
        reports = {finding.title: finding for finding in operations_findings(True, now)}
        self.assertEqual(reports["Payment reconciliation"].status, Status.ACTION)
        self.assertNotIn(str(latest.id), reports["Payment reconciliation"].evidence)


class AdvisorEvidenceTests(SimpleTestCase):
    def test_release_uses_exact_commit_and_links_only_to_github(self):
        sha = "a" * 40
        other_run = {"head_sha": "b" * 40, "conclusion": "success", "id": 99}
        self.assertEqual(release_finding(sha, other_run).status, Status.VERIFY)
        verified = {**other_run, "head_sha": sha, "html_url": "https://untrusted.example/"}
        self.assertEqual(release_finding(sha, verified).status, Status.PASS)
        self.assertTrue(release_finding(sha, verified).url.endswith("/actions/runs/99"))
        self.assertEqual(release_finding(sha, {**verified, "conclusion": "failure"}).status, Status.ACTION)

    def test_backup_requires_scheduled_current_production_evidence(self):
        now = timezone.now()
        run = {
            "id": 24,
            "event": "schedule",
            "head_branch": "main",
            "conclusion": "success",
            "updated_at": (now - timedelta(days=1)).isoformat(),
        }
        self.assertEqual(backup_finding(now, run).status, Status.PASS)
        self.assertEqual(backup_finding(now, {**run, "event": "workflow_dispatch"}).status, Status.VERIFY)
        self.assertEqual(backup_finding(now, {**run, "updated_at": "invalid"}).status, Status.VERIFY)
        self.assertEqual(backup_finding(now, {**run, "conclusion": "failure"}).status, Status.ACTION)
        old = {**run, "updated_at": (now - timedelta(days=36)).isoformat()}
        self.assertEqual(backup_finding(now, old).status, Status.ACTION)

    @override_settings(PUBLIC_SITE_URL="https://example.test")
    @patch("amaris_cms.advisor_evidence._read_json")
    def test_frontend_requires_the_expected_probe_response(self, read):
        read.return_value = {"status": "ok"}
        self.assertEqual(frontend_probe(), "unavailable")
        read.return_value = {"status": "ok", "service": "amaris-student-frontend"}
        self.assertEqual(frontend_probe(), "reachable")
        self.assertEqual(read.call_args.args[0], "https://example.test/health/ready")

    @patch("amaris_cms.advisor_evidence._read_json", return_value={"workflow_runs": []})
    def test_workflow_evidence_uses_allowlisted_api_requests(self, read):
        self.assertIsNone(latest_workflow_run(BACKUP_WORKFLOW, branch="main", event="schedule"))
        self.assertIn("branch=main&event=schedule", read.call_args.args[0])
        with self.assertRaises(ValueError):
            latest_workflow_run("other.yml")
        read.assert_called_once()

    @override_settings(SUPABASE_DATABASE_REQUIRED=True)
    @patch("amaris_cms.trusted_advisor.connection")
    def test_missing_or_public_storage_and_api_grants_are_flagged(self, connection):
        connection.vendor = "postgresql"
        cursor = connection.cursor.return_value.__enter__.return_value
        stores = {
            **TEST_STORAGES,
            **{
                alias: {
                    "BACKEND": "amaris_cms.storage.SupabaseS3Storage",
                    "OPTIONS": {"querystring_auth": True, "bucket_name": name},
                }
                for alias, name in (("default", "admins"), ("student_private", "students"))
            },
        }
        with override_settings(
            STORAGES=stores,
            SUPABASE_S3_STUDENT_BUCKET="students",
            SUPABASE_S3_ADMIN_BUCKET="admins",
            SUPABASE_PROJECT_REF="test-project",
            SUPABASE_S3_ENDPOINT_URL="https://test-project.storage.supabase.co",
        ):
            cursor.fetchall.return_value = [("students", False), ("admins", True)]
            self.assertEqual(storage_finding(True).status, Status.ACTION)
            cursor.fetchall.return_value = [("students", False), ("admins", False)]
            self.assertEqual(storage_finding(True).status, Status.PASS)
            with override_settings(SUPABASE_S3_ENDPOINT_URL="https://other-project.storage.supabase.co"):
                self.assertEqual(storage_finding(True).status, Status.VERIFY)
        cursor.fetchall.return_value = [(True, False, 2)] * 6 + [(False, True, 2)]
        self.assertEqual(table_access_finding(True).status, Status.ACTION)
        cursor.fetchall.return_value = [(True, False, 2)] * 6 + [(True, True, 2)]
        self.assertEqual(table_access_finding(True).status, Status.VERIFY)

    @patch("amaris_cms.trusted_advisor.latest_workflow_run", return_value=None)
    @patch("amaris_cms.trusted_advisor.monitor_statuses", return_value=[])
    @patch("amaris_cms.trusted_advisor.frontend_probe", return_value="unavailable")
    @patch("amaris_cms.trusted_advisor.broker_available", return_value=False)
    @patch("amaris_cms.trusted_advisor.database_available", return_value=False)
    def test_reports_degrade_safely_and_cli_returns_same_findings(self, *mocks):
        report = collect_advisor_report()
        findings = {finding.title: finding for finding in report.findings}
        self.assertEqual(findings["Primary database"].status, Status.ACTION)
        self.assertEqual(findings["Payment reconciliation"].status, Status.VERIFY)
        self.assertEqual(findings["Production database backup and restore"].status, Status.VERIFY)
        self.assertEqual(sum(report.counts.values()), len(report.findings))
        output = StringIO()
        call_command("trusted_advisor", stdout=output)
        self.assertEqual(json.loads(output.getvalue())["counts"], report.counts)
