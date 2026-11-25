"""Read-only governance findings from Django and the platform's existing evidence."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from urllib.parse import urlsplit

from django.conf import settings
from django.core.checks import run_checks
from django.db import DatabaseError, connection
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from content.models import (
    LiveClassBooking,
    Payment,
    PaymentReconciliationRun,
    StudentRecord,
    TutorApplicationDocument,
    VideoRequest,
    WebVitalBucket,
)
from content.payment_models import Invoice, NotificationOutbox

from .advisor_evidence import (
    BACKUP_WORKFLOW,
    QUALITY_WORKFLOW,
    deployed_sha,
    frontend_probe,
    latest_workflow_run,
    workflow_url,
)
from .health import broker_available, database_available
from .monitoring_status import monitor_statuses

RENDER_DASHBOARD = "https://dashboard.render.com"
SUPABASE_DASHBOARD = "https://supabase.com/dashboard/projects"
GRAFANA_INDEX = "admin:amaris_monitoring_home"


class Status(StrEnum):
    ACTION = "Action required"
    VERIFY = "Needs verification"
    PASS = "Passed"


@dataclass(frozen=True)
class Finding:
    category: str
    title: str
    status: Status
    evidence: str
    next_step: str = ""
    url: str = ""
    link_label: str = ""


@dataclass(frozen=True)
class AdvisorReport:
    checked_at: datetime
    findings: list[Finding]
    counts: dict[str, int]


def security_findings() -> list[Finding]:
    checks = sorted({str(check.id) for check in run_checks(include_deployment_checks=True) if check.id})
    django = Finding(
        "Security",
        "Django deployment settings",
        Status.ACTION if checks else Status.PASS,
        "Django reported " + ", ".join(checks) + "." if checks else "Django's deployment checks reported no issues.",
        "Review the flagged deployment settings." if checks else "",
    )
    auth_configured = bool(settings.SUPABASE_URL and settings.SUPABASE_PUBLISHABLE_KEY)
    auth = Finding(
        "Authentication",
        "Supabase sign-in and email verification",
        Status.VERIFY if auth_configured else Status.ACTION,
        (
            "Django has the required Auth configuration. Sign-in, verification codes and password recovery "
            "need an end-to-end check."
            if auth_configured
            else "Supabase Auth configuration is incomplete in this environment."
        ),
        "Verify registration, six-digit email confirmation, sign-in and password recovery with a test account.",
        SUPABASE_DASHBOARD,
        "Open Supabase",
    )
    return [django, auth]


def _uses_signed_bucket(alias: str, name: str) -> bool:
    config = settings.STORAGES.get(alias)
    if not isinstance(config, dict) or config.get("BACKEND") != "amaris_cms.storage.SupabaseS3Storage":
        return False
    options = config.get("OPTIONS")
    return isinstance(options, dict) and options.get("bucket_name") == name and options.get("querystring_auth") is True


def _storage_uses_database_project() -> bool:
    ref = settings.SUPABASE_PROJECT_REF.strip().lower()
    try:
        host = urlsplit(settings.SUPABASE_S3_ENDPOINT_URL).hostname
    except ValueError:
        return False
    return bool(ref and host in (f"{ref}.storage.supabase.co", f"{ref}.supabase.co"))


def storage_finding(db_ok: bool) -> Finding:
    category, title = "Data protection", "Private student and admin storage"
    admin_bucket = settings.SUPABASE_S3_ADMIN_BUCKET
    student_bucket = settings.SUPABASE_S3_STUDENT_BUCKET
    supported = _uses_signed_bucket("default", admin_bucket) and _uses_signed_bucket("student_private", student_bucket)
    buckets = {admin_bucket, student_bucket} - {""}
    link = (SUPABASE_DASHBOARD, "Open Supabase")
    action = "Check the configured student and admin buckets and verify authorized upload and download."
    if not supported or len(buckets) != 2:
        return Finding(
            category,
            title,
            Status.ACTION,
            "Django requires two distinct configured buckets with signed downloads for this check.",
            action,
            *link,
        )
    if (
        db_ok
        and connection.vendor == "postgresql"
        and settings.SUPABASE_DATABASE_REQUIRED
        and _storage_uses_database_project()
    ):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id, public FROM storage.buckets WHERE id = ANY(%s)", [list(buckets)])
                records = dict(cursor.fetchall())
        except DatabaseError:
            records = None
        if records is not None:
            if set(records) != buckets or any(records.values()):
                return Finding(
                    category,
                    title,
                    Status.ACTION,
                    "A configured student or admin bucket is missing or public.",
                    action,
                    *link,
                )
            return Finding(
                category,
                title,
                Status.PASS,
                "The configured student and admin buckets are private and Django uses signed URLs.",
                "",
                *link,
            )
    return Finding(
        category,
        title,
        Status.VERIFY,
        "Signed storage is configured; bucket privacy could not be verified.",
        action,
        *link,
    )


def table_access_finding(db_ok: bool) -> Finding:
    category, title = "Data protection", "Supabase API access to sensitive tables"
    action = "Review direct grants and row-level security policies in Supabase."
    link = (SUPABASE_DASHBOARD, "Open Supabase")
    unverified = Finding(
        category,
        title,
        Status.VERIFY,
        "The advisor could not verify the expected Supabase table grants.",
        action,
        *link,
    )
    if not db_ok or connection.vendor != "postgresql" or not settings.SUPABASE_DATABASE_REQUIRED:
        return unverified

    records = (
        StudentRecord,
        LiveClassBooking,
        VideoRequest,
        Payment,
        Invoice,
        NotificationOutbox,
        TutorApplicationDocument,
    )
    tables = [model._meta.db_table for model in records]
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT c.relrowsecurity,
                       EXISTS (
                           SELECT 1 FROM pg_roles r WHERE r.rolname IN ('anon', 'authenticated')
                           AND (
                               has_table_privilege(r.oid, c.oid, 'SELECT, INSERT, UPDATE, DELETE')
                               OR has_any_column_privilege(r.oid, c.oid, 'SELECT, INSERT, UPDATE')
                           )
                       ),
                       (SELECT count(*) FROM pg_roles WHERE rolname IN ('anon', 'authenticated'))
                FROM unnest(%s::text[]) AS expected(table_name)
                JOIN pg_class c ON c.oid = to_regclass(expected.table_name)
                """,
                [tables],
            )
            grants = cursor.fetchall()
    except DatabaseError:
        return unverified
    if len(grants) != len(tables) or any(role_count != 2 for _, _, role_count in grants):
        return unverified
    if any(has_access and not has_rls for has_rls, has_access, _ in grants):
        return Finding(
            category,
            title,
            Status.ACTION,
            "A checked table has an API role grant with row-level security disabled.",
            action,
            *link,
        )
    if any(has_access for _, has_access, _ in grants):
        return Finding(
            category,
            title,
            Status.VERIFY,
            "A checked table has an API role grant with row-level security enabled.",
            "Verify the applicable policies enforce record ownership.",
            *link,
        )
    return Finding(
        category,
        title,
        Status.PASS,
        "The anonymous and authenticated Supabase API roles have no direct data grants on the checked tables.",
        "",
        *link,
    )


def operations_findings(db_ok: bool, now: datetime) -> list[Finding]:
    unavailable = "The advisor could not read the operational records."
    review = queue = reconciliation = meeting_links = (Status.VERIFY, unavailable)
    if db_ok:
        try:
            booking_review = LiveClassBooking.objects.filter(status=LiveClassBooking.Status.PAYMENT_REVIEW).exists()
            video_review = VideoRequest.objects.filter(status=VideoRequest.Status.PAYMENT_REVIEW).exists()
            review = (
                (Status.ACTION, "A live-class booking or video request is awaiting payment review.")
                if booking_review or video_review
                else (Status.PASS, "No bookings or video requests are marked for payment review.")
            )
            failed = NotificationOutbox.objects.filter(status=NotificationOutbox.Status.FAILED).exists()
            overdue = NotificationOutbox.objects.filter(
                status=NotificationOutbox.Status.QUEUED, created_at__lt=now - timedelta(minutes=15)
            ).exists()
            queue = (
                (Status.ACTION, "A payment email failed or has been queued for more than 15 minutes.")
                if failed or overdue
                else (Status.PASS, "No failed or overdue payment emails appear in the payment outbox.")
            )
            missing_link = LiveClassBooking.objects.filter(
                status=LiveClassBooking.Status.CONFIRMED, slot__starts_at__gte=now, slot__zoom_join_url=""
            ).exists()
            meeting_links = (
                (Status.ACTION, "An upcoming confirmed booking has no Zoom join link.")
                if missing_link
                else (Status.PASS, "No upcoming confirmed bookings are missing a Zoom join link.")
            )
            latest = PaymentReconciliationRun.objects.order_by("-started_at").first()
            if latest and (latest.status == PaymentReconciliationRun.Status.FAILED or latest.unresolved_count):
                reconciliation = (Status.ACTION, "The latest reconciliation failed or left unresolved payments.")
            elif (
                latest
                and latest.status == PaymentReconciliationRun.Status.SUCCEEDED
                and latest.completed_at
                and (now - timedelta(minutes=20) <= latest.completed_at <= now)
            ):
                reconciliation = (Status.PASS, "The latest completed reconciliation finished within 20 minutes.")
            else:
                reconciliation = (
                    Status.VERIFY,
                    "A successful reconciliation in the past 20 minutes could not be verified.",
                )
        except DatabaseError:
            pass
    return [
        Finding(
            "Classes",
            "Upcoming booked lessons",
            *meeting_links,
            "Review Zoom links in the affected bookings." if meeting_links[0] != Status.PASS else "",
            reverse("admin:content_liveclassbooking_changelist"),
            "Open live-class bookings",
        ),
        Finding(
            "Payments",
            "Booking and video payment review",
            *review,
            "Review the affected records in Django Admin." if review[0] != Status.PASS else "",
        ),
        Finding(
            "Payments",
            "Payment reconciliation",
            *reconciliation,
            "Check Celery Beat and the payment reconciliation runs." if reconciliation[0] != Status.PASS else "",
            reverse("admin:content_paymentreconciliationrun_changelist"),
            "Open reconciliation runs",
        ),
        Finding(
            "Notifications",
            "Payment email outbox",
            *queue,
            (
                "Check the notification worker and verify email delivery to the intended recipients."
                if queue[0] != Status.PASS
                else ""
            ),
            reverse("admin:content_notificationoutbox_changelist"),
            "Open notification outbox",
        ),
    ]


def monitoring_findings(services: list[dict]) -> list[Finding]:
    results = []
    for service in services:
        result = service["status"]
        if result == "reachable":
            status = Status.PASS
            evidence = {
                "flower": "Flower reports at least one active Celery worker.",
                "render": "The exporter reports a successful refresh within five minutes.",
            }.get(service["name"], "The private monitoring endpoint responded.")
            next_step = ""
        elif result == "unconfigured":
            status, evidence = Status.VERIFY, "The private monitoring check is disabled or unconfigured."
            next_step = "Connect the existing private service to the monitoring dashboard."
        else:
            status, evidence = Status.ACTION, "The configured monitoring signal is unavailable, invalid or degraded."
            next_step = "Open private monitoring and inspect the service status."
        results.append(
            Finding(
                "Monitoring", service["title"], status, evidence, next_step, reverse(GRAFANA_INDEX), "Open monitoring"
            )
        )
    return results


def release_finding(sha: str | None, run: dict | None) -> Finding:
    verified = run if sha and run and run.get("head_sha") == sha else None
    conclusion = verified.get("conclusion") if verified else None
    if conclusion == "success" and sha:
        status, evidence = Status.PASS, f"GitHub reported success for the deployed revision {sha[:12]}."
    elif conclusion in ("failure", "timed_out", "action_required") and sha:
        status, evidence = Status.ACTION, f"GitHub reported an unsuccessful quality run for revision {sha[:12]}."
    else:
        status, evidence = (
            Status.VERIFY,
            "A successful quality run for the exact deployed revision could not be verified.",
        )
    return Finding(
        "Releases",
        "Deployed backend CI evidence",
        status,
        evidence,
        "Verify the release candidate and required checks before promotion." if status != Status.PASS else "",
        workflow_url(QUALITY_WORKFLOW, verified),
        "Open GitHub Actions",
    )


def backup_finding(now: datetime, run: dict | None) -> Finding:
    verified = run if run and run.get("event") == "schedule" and run.get("head_branch") == "main" else None
    status, evidence = (
        Status.VERIFY,
        "A successful scheduled production application-schema backup could not be verified.",
    )
    if verified and verified.get("conclusion") == "success":
        try:
            checked = parse_datetime(str(verified.get("updated_at") or ""))
        except ValueError:
            checked = None
        if checked and timezone.is_aware(checked) and checked <= now:
            if checked >= now - timedelta(days=35):
                status = Status.PASS
                date = timezone.localtime(checked).date()
                evidence = f"The production application-schema backup and isolated restore workflow passed on {date}."
            else:
                status, evidence = (
                    Status.ACTION,
                    "The latest successful scheduled backup evidence is older than 35 days.",
                )
    elif verified and verified.get("conclusion") in ("failure", "timed_out", "action_required"):
        status, evidence = Status.ACTION, "The latest scheduled production backup and restore workflow failed."
    return Finding(
        "Recovery",
        "Production database backup and restore",
        status,
        evidence,
        "Check the scheduled backup run and retain restore evidence." if status != Status.PASS else "",
        workflow_url(BACKUP_WORKFLOW, verified),
        "Open backup workflow",
    )


def performance_finding(db_ok: bool, now: datetime) -> Finding:
    status, evidence = Status.VERIFY, "Recent aggregate browser performance measurements could not be verified."
    if db_ok and settings.RUM_PERSIST_ENABLED:
        try:
            if WebVitalBucket.objects.filter(
                day__range=(timezone.localdate(now) - timedelta(days=2), timezone.localdate(now)), count__gt=0
            ).exists():
                status, evidence = Status.PASS, "The database has recent aggregate browser performance samples."
        except DatabaseError:
            pass
    return Finding(
        "Performance",
        "Browser performance telemetry",
        status,
        evidence,
        "Review LCP, INP and CLS by device in the private dashboards.",
        reverse(GRAFANA_INDEX),
        "Open monitoring",
    )


def collect_advisor_report() -> AdvisorReport:
    now = timezone.now()
    sha = deployed_sha()
    with ThreadPoolExecutor(max_workers=5) as pool:
        frontend = pool.submit(frontend_probe)
        broker = pool.submit(broker_available)
        monitoring = pool.submit(monitor_statuses)
        quality = pool.submit(latest_workflow_run, QUALITY_WORKFLOW, head_sha=sha) if sha else None
        backup = pool.submit(latest_workflow_run, BACKUP_WORKFLOW, branch="main", event="schedule")
        db_ok = database_available()
        site_ok = frontend.result() == "reachable"
        redis_ok = broker.result()
        findings = [
            Finding(
                "Infrastructure",
                "Student website",
                Status.PASS if site_ok else Status.ACTION,
                (
                    "The frontend readiness endpoint responded correctly."
                    if site_ok
                    else "The frontend readiness endpoint could not be verified."
                ),
                "Check the frontend service and configured website URL." if not site_ok else "",
                RENDER_DASHBOARD,
                "Open Render",
            ),
            Finding(
                "Infrastructure",
                "Primary database",
                Status.PASS if db_ok else Status.ACTION,
                "Django completed a database query." if db_ok else "Django could not complete a database query.",
                "Check the database service and Django connection." if not db_ok else "",
                SUPABASE_DASHBOARD,
                "Open Supabase",
            ),
            Finding(
                "Infrastructure",
                "Redis / Celery broker",
                Status.PASS if redis_ok else Status.ACTION,
                "The configured broker responded to a ping." if redis_ok else "The configured broker did not respond.",
                "Check the broker and notification services in Render." if not redis_ok else "",
                RENDER_DASHBOARD,
                "Open Render",
            ),
            *security_findings(),
            storage_finding(db_ok),
            table_access_finding(db_ok),
            *operations_findings(db_ok, now),
            *monitoring_findings(monitoring.result()),
            release_finding(sha, quality.result() if quality else None),
            backup_finding(now, backup.result()),
            performance_finding(db_ok, now),
            Finding(
                "Cost and capacity",
                "Hosting spend and headroom",
                Status.VERIFY,
                "This report has no verified billing totals or capacity test evidence.",
                "Review Render billing and service limits alongside Supabase usage and the latest load tests.",
                RENDER_DASHBOARD,
                "Open Render",
            ),
        ]
    counts = Counter(item.status for item in findings)
    rank = {status: index for index, status in enumerate(Status)}
    return AdvisorReport(
        now,
        sorted(findings, key=lambda item: rank[item.status]),
        {
            "action": counts[Status.ACTION],
            "verify": counts[Status.VERIFY],
            "passed": counts[Status.PASS],
        },
    )
