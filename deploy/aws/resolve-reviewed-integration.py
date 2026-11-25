"""Resolve only reviewed sponsor/subscription integration conflicts.

Run from the candidate worktree after git apply --3way reports conflicts.
Unexpected paths or source changes fail closed.
"""
import subprocess
import sys
from pathlib import Path


def git(*args):
    return subprocess.check_output(["git", *args], text=True)


def once(text, before, after):
    if text.count(before) != 1:
        raise SystemExit(f"Expected exactly one anchor: {before!r}")
    return text.replace(before, after, 1)


def insert(text, anchor, addition):
    return once(text, anchor, addition + anchor)


def resolve_backend(path, text):
    if path == "backend/.env.example":
        return text.rstrip() + "\n\n# Enable only after isolated end-of-term PDF/storage/SMTP acceptance.\nSUBSCRIPTION_REPORTS_EMAIL_ENABLED=false\n"
    if path == "backend/amaris_cms/celery.py":
        return insert(text, '    "content.tasks.queue_student_motivation_emails":', '    "content.subscription_report_tasks.deliver_ended_subscription_reports": {"queue": "notifications"},\n')
    if path == "backend/amaris_cms/settings.py":
        text = once(text, 'TUTOR_REQUIRE_SIX_DOCUMENTS = env_bool("TUTOR_REQUIRE_SIX_DOCUMENTS", False)\n', 'TUTOR_REQUIRE_SIX_DOCUMENTS = env_bool("TUTOR_REQUIRE_SIX_DOCUMENTS", False)\nCOURSE_SUBSCRIPTIONS_ENABLED = env_bool("COURSE_SUBSCRIPTIONS_ENABLED", False)\n')
        text = once(text, "\nCELERY_BEAT_SCHEDULE = {", '\nSUBSCRIPTION_REPORTS_EMAIL_ENABLED = env_bool("SUBSCRIPTION_REPORTS_EMAIL_ENABLED", False)\nif SUBSCRIPTION_REPORTS_EMAIL_ENABLED and not DEBUG and not SUPABASE_S3_ENDPOINT_URL:\n    raise RuntimeError("Subscription reports require private Supabase student storage in production.")\n\nCELERY_BEAT_SCHEDULE = {')
        return once(text, '\nCELERY_BEAT_SCHEDULE = {\n', '\nCELERY_BEAT_SCHEDULE = {\n    "deliver-ended-subscription-reports": {\n        "task": "content.subscription_report_tasks.deliver_ended_subscription_reports",\n        "schedule": 600.0,\n        "options": {"queue": "notifications"},\n    },\n')
    if path == "backend/content/apps.py":
        text = once(text, "from . import payment_models, sponsor_models, tutor_finance_models  # noqa: F401", "from . import payment_models, sponsor_models, subscription_models, subscription_report_models, tutor_finance_models")
        text = once(text, "from . import payment_admin, schema, signals, sponsor_admin, tutor_finance_admin  # noqa: F401", "from . import payment_admin, schema, signals, sponsor_admin, subscription_admin, subscription_report_admin, tutor_finance_admin")
        return "# ruff: noqa: F401\n" + text
    if path == "backend/content/payfast_views.py":
        return once(text, '        if local_reference.startswith("SC-"):', '        if local_reference.startswith("SUB-"):\n            from .services.subscriptions import process_subscription_notification\n\n            result = process_subscription_notification(payload, gateway=gateway)\n        elif local_reference.startswith("SC-"):')
    if path == "backend/content/test_booking_migration.py":
        # Sponsor already restores every migration leaf and adds notification tests.
        if "MigrationExecutor(connection).migrate(latest)" not in text or "queue_student_motivation_emails" not in text:
            raise SystemExit("Migration test no longer matches reviewed sponsor version")
        return text
    if path == "backend/content/urls.py":
        text = insert(text, "from .tutor_application_views import (", """from .subscription_report_views import (
    SubscriptionReportDownloadView,
    TutorSubscriptionSessionListView,
    TutorSubscriptionSessionView,
)
from .subscription_views import (
    SubscriptionCheckoutView,
    SubscriptionInvoiceView,
    SubscriptionListView,
    SubscriptionStatusView,
)
""")
        return once(text, "urlpatterns = [\n", """urlpatterns = [
    path(
        "student/subscriptions/<str:reference>/report/",
        SubscriptionReportDownloadView.as_view(),
        name="subscription-report",
    ),
    path(
        "tutor/subscription-sessions/<int:session_id>/attendance/",
        TutorSubscriptionSessionView.as_view(),
        name="subscription-attendance",
    ),
    path(
        "tutor/subscription-sessions/", TutorSubscriptionSessionListView.as_view(), name="subscription-tutor-sessions"
    ),
    path("student/subscriptions/", SubscriptionListView.as_view(), name="student-subscriptions"),
    path("student/subscriptions/checkout/", SubscriptionCheckoutView.as_view(), name="subscription-checkout"),
    path("student/subscriptions/<str:reference>/", SubscriptionStatusView.as_view(), name="subscription-status"),
    path(
        "student/subscriptions/<str:reference>/invoice/", SubscriptionInvoiceView.as_view(), name="subscription-invoice"
    ),
""")
    raise SystemExit(f"Unreviewed backend conflict: {path}")



def resolve_tutor(path, ours, theirs):
    if path == "backend/.env.example":
        return ours.rstrip() + "\n\n# Tutor portal video submissions remain off until private upload/SMTP acceptance.\nTUTOR_VIDEO_UPLOADS_ENABLED=false\nTUTOR_VIDEO_MAX_UPLOAD_BYTES=52428800\n# Empty uses the academy email in Django Site Settings. Never take this from a request.\nTUTOR_VIDEO_ADMIN_EMAIL=\nTUTOR_PERSONNEL_FORMS_ENABLED=false\nTUTOR_PERSONNEL_ADMIN_EMAIL=\n"
    if path == "backend/amaris_cms/celery.py":
        return insert(ours, '    "content.subscription_report_tasks.deliver_ended_subscription_reports":', '    "content.tutor_personnel_tasks.deliver_tutor_personnel_forms": {"queue": "notifications"},\n    "content.tutor_video_tasks.deliver_tutor_video_admin_alerts": {"queue": "notifications"},\n')
    if path == "backend/amaris_cms/settings.py":
        start = theirs.index("TUTOR_VIDEO_UPLOADS_ENABLED =")
        end = theirs.index("\nCELERY_BEAT_SCHEDULE = {", start)
        settings = theirs[start:end].replace('PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", "").strip()\n', "")
        ours = once(ours, "\nCELERY_BEAT_SCHEDULE = {\n", "\n" + settings + "\nCELERY_BEAT_SCHEDULE = {\n")
        start = theirs.index('    "tutor-personnel-admin-alerts": {')
        end = theirs.index('    "reconcile-tutor-earnings": {', start)
        return insert(ours, '    "deliver-ended-subscription-reports": {', theirs[start:end])
    if path == "backend/content/apps.py":
        ours = once(ours, "subscription_report_models, tutor_finance_models", "subscription_report_models, tutor_finance_models, tutor_personnel_models, tutor_video_models")
        return once(ours, "subscription_report_admin, tutor_finance_admin", "subscription_report_admin, tutor_finance_admin, tutor_personnel_admin, tutor_video_admin")
    if path == "backend/content/tasks.py":
        anchor = '@shared_task(ignore_result=True, queue="notifications")\ndef queue_student_motivation_emails():'
        if ours.count(anchor) != 1:
            raise SystemExit("Motivation task anchor changed")
        extra = ours[ours.index(anchor):]
        theirs = once(theirs, "from . import tutor_finance_tasks, tutor_personnel_tasks, tutor_video_tasks", "from . import subscription_report_tasks, tutor_finance_tasks, tutor_personnel_tasks, tutor_video_tasks")
        return theirs.rstrip() + "\n\n\n" + extra
    if path == "backend/content/test_booking_migration.py":
        if "MigrationExecutor(connection).migrate(latest)" not in ours:
            raise SystemExit("Full schema restoration missing")
        return ours
    if path == "backend/content/urls.py":
        ours = insert(ours, "from .tutor_views import", "from .tutor_personnel_views import TutorPersonnelFormsView, TutorPersonnelPDFView\nfrom .tutor_video_views import TutorVideoView\n")
        return once(ours, "urlpatterns = [\n", """urlpatterns = [
    path("tutor/videos/", TutorVideoView.as_view(), name="tutor-videos"),
    path("tutor/forms/", TutorPersonnelFormsView.as_view(), name="tutor-personnel-forms"),
    path("tutor/forms/<uuid:form_id>/pdf/", TutorPersonnelPDFView.as_view(), name="tutor-personnel-pdf"),
""")
    raise SystemExit(f"Unreviewed tutor conflict: {path}")



def resolve_payment_frontend(path, ours):
    if path.endswith("/student-api.ts"):
        pairs = [
            ("checkoutKey(courseSlug: string)", 'checkoutKey(courseSlug: string, provider: "payfast" | "paystack")'),
            ('encode(\x60${student.id}:${courseSlug}\x60)', 'encode(\x60${student.id}:${courseSlug}${provider === "payfast" ? "" : ":paystack"}\x60)'),
            ("createStudentCheckout(courseSlug: string)", 'createStudentCheckout(courseSlug: string, provider: "payfast" | "paystack" = "payfast")'),
            ("idempotency_key: await checkoutKey(courseSlug),", "idempotency_key: await checkoutKey(courseSlug, provider),\n      provider,"),
            ("liveClassCheckoutKey(slotId: string, topic: string, attempt: string)", 'liveClassCheckoutKey(slotId: string, topic: string, attempt: string, provider: "payfast" | "paystack")'),
            ('encode(\x60${student.id}:${slotId}:${normalizedTopic}:${attempt}\x60)', 'encode(\x60${student.id}:${slotId}:${normalizedTopic}:${attempt}${provider === "payfast" ? "" : ":paystack"}\x60)'),
            ("  attempt: string,\n): Promise<LiveClassCheckoutSession>", '  attempt: string,\n  provider: "payfast" | "paystack" = "payfast",\n): Promise<LiveClassCheckoutSession>'),
            ("idempotency_key: await liveClassCheckoutKey(slotId, topic, attempt),", "idempotency_key: await liveClassCheckoutKey(slotId, topic, attempt, provider),\n      provider,"),
        ]
        for before, after in pairs:
            ours = once(ours, before, after)
        return ours
    live = "/book-online-live-class/" in path
    if live:
        anchor = "  await requireVerifiedStudent(returnTo);\n"
        selection = '  const selected = process.env.PAYSTACK_ENABLED === "true" ? value(params.provider) : "payfast";\n'
        base = "returnTo"
        ours = once(ours, "createStudentLiveClassCheckout(slotId, topic, attempt)", "createStudentLiveClassCheckout(slotId, topic, attempt, selected)")
        ours = once(ours, "Your Zoom link is released only after the server verifies the PayFast notification.", "Your Zoom link is released only after the server verifies payment with the selected provider.")
        button = "Pay R{booking.amount} with Paystack"
        separator = "&"
    else:
        ours = once(ours, "CheckoutPage({ params }: { params: Promise<{ slug: string }> })", "CheckoutPage({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<{ provider?: string }> })")
        anchor = "  const { slug } = await params;\n"
        selection = '  const selected = process.env.PAYSTACK_ENABLED === "true" ? (await searchParams).provider : "payfast";\n'
        base = '\x60/checkout/${encodeURIComponent(slug)}\x60'
        ours = once(ours, "createStudentCheckout(slug)", "createStudentCheckout(slug, selected)")
        ours = once(ours, "Access is activated only after the server verifies the PayFast notification.", "Access is activated only after the server verifies payment with the selected provider.")
        button = "Continue to Paystack"
        separator = "?"
    selection += '  if (selected !== "payfast" && selected !== "paystack") {\n'
    selection += "    const base = " + base + ";\n"
    selection += ('    return <main className="min-h-screen bg-[#f5f7fb]"><Header /><section className="mx-auto max-w-xl px-5 py-16"><h1 className="text-3xl font-semibold">Choose your payment method</h1><p className="my-5">Confirmation follows verified payment.</p><div className="grid gap-4"><Link href={base + "' + separator + 'provider=payfast"} className="rounded-xl bg-[#0b2a5b] p-5 text-center font-bold text-white">Pay with PayFast</Link><Link href={base + "' + separator + 'provider=paystack"} className="rounded-xl border border-[#0b2a5b] p-5 text-center font-bold text-[#0b2a5b]">Pay with Paystack</Link></div></section><Footer /></main>;\n  }\n')
    ours = once(ours, anchor, anchor + selection)
    ours = once(ours, '<form method="post" action={checkout.gateway_url} className="mt-7">', '{selected === "paystack" ? <a href={checkout.gateway_url} className="mt-7 flex min-h-12 items-center justify-center rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white">' + button + '</a> : <form method="post" action={checkout.gateway_url} className="mt-7">')
    return once(ours, "</form>", "</form>}")



BACKEND = {
    "backend/.env.example", "backend/amaris_cms/celery.py",
    "backend/amaris_cms/settings.py", "backend/content/apps.py",
    "backend/content/payfast_views.py", "backend/content/test_booking_migration.py",
    "backend/content/urls.py",
}
FRONTEND = {"frontend/lib/supabase/proxy.ts", "frontend/worker/index.ts"}


def main():
    component, ref, sha = sys.argv[1:]
    if (component, ref) == ("backend", "feat/curriculum-subscriptions-backend-20261112"):
        expected = BACKEND
    elif (component, ref) == ("backend", "feat/tutor-video-admin-alerts-20261113"):
        expected = (BACKEND - {"backend/content/payfast_views.py"}) | {"backend/content/tasks.py"}
    elif (component, ref) == ("backend", "feat/tutor-employment-contract-backend-20261115"):
        expected = {"backend/content/apps.py"}
    elif (component, ref) == ("frontend", "feature/paystack-payfast-choice-20261110"):
        expected = {"frontend/app/book-online-live-class/checkout/page.tsx", "frontend/app/checkout/[slug]/page.tsx", "frontend/lib/student-api.ts"}
    elif (component, ref) == ("backend", "feat/admin-fortnightly-performance-20261113"):
        expected = {"backend/content/apps.py", "backend/content/tasks.py"}
    elif (component, ref) == ("frontend", "feat/private-chat-ui-20261124"):
        expected = {"frontend/components/site/dashboard-navigation.tsx", "frontend/proxy.ts", "frontend/worker/index.ts"}
    elif (component, ref) == ("frontend", "feat/sponsor-dashboard-20261111"):
        expected = FRONTEND
    elif (component, ref) == ("frontend", "feat/course-search-ui-20261118"):
        expected = {"frontend/app/page.tsx"}
    else:
        raise SystemExit("No reviewed resolution for this feature")
    paths = set(git("diff", "--name-only", "--diff-filter=U").splitlines())
    if paths != expected:
        raise SystemExit(f"Unexpected conflict set: {sorted(paths)}")
    # Reject changed source revisions: compare exact staged incoming blobs with
    # the source tree; the explicit anchors also guard the existing candidate.
    for path in sorted(paths):
        ours = git("show", f":2:{path}")
        theirs = git("show", f":3:{path}")
        source = git("show", f"{sha}:{path}")
        if theirs != source:
            raise SystemExit(f"Incoming blob differs from reviewed source: {path}")
        if ref == "feat/tutor-employment-contract-backend-20261115":
            resolved = once(ours, "from . import payment_models,", "from . import payment_models, tutor_contract_models,")
            resolved = once(resolved, "from . import payment_admin,", "from . import payment_admin, tutor_contract_admin,")
        elif ref == "feature/paystack-payfast-choice-20261110" and component == "frontend":
            resolved = resolve_payment_frontend(path, ours)
        elif ref == "feat/admin-fortnightly-performance-20261113":
            if path.endswith("/apps.py"):
                resolved = once(ours, "from . import payment_models,", "from . import payment_models, performance_models,")
                resolved = once(resolved, "from . import payment_admin,", "from . import payment_admin, performance_admin,")
            else:
                resolved = once(ours, "from . import subscription_report_tasks,", "from . import performance_tasks, subscription_report_tasks,")
        elif ref == "feat/private-chat-ui-20261124":
            if path.endswith("dashboard-navigation.tsx"):
                resolved = once(ours, "  LayoutDashboard,\n", "  LayoutDashboard,\n  MessageSquare,\n")
                resolved = once(resolved, ' | "subscriptions";', ' | "subscriptions" | "messages";')
                resolved = insert(resolved, '  { key: "notifications",', '  { key: "messages", label: "Messages", href: "/dashboard/messages", icon: MessageSquare },\n')
            elif path == "frontend/proxy.ts":
                resolved = once(ours, '    "/dashboard/:path*",\n', '    "/dashboard/:path*",\n    "/api/chat/:path*",\n')
            else:
                resolved = once(ours, '"/dashboard",', '"/dashboard", "/api/chat",')
        elif ref == "feat/tutor-video-admin-alerts-20261113":
            resolved = resolve_tutor(path, ours, theirs)
        elif component == "backend":
            resolved = resolve_backend(path, ours)
        elif ref == "feat/course-search-ui-20261118":
            if "getManagedFeaturedCourses" not in theirs or "<CourseSubscriptions />" not in ours:
                raise SystemExit("Homepage feature anchors missing")
            resolved = once(ours, 'import { getManagedCourses } from "@/lib/cms";', 'import { getManagedFeaturedCourses } from "@/lib/cms";')
            resolved = once(resolved, "await getManagedCourses()", "await getManagedFeaturedCourses()")
        else:
            if '"/sponsor"' not in theirs or '"/subscriptions/status"' not in ours:
                raise SystemExit(f"Private-route anchors missing: {path}")
            resolved = once(ours, '"/dashboard",', '"/dashboard", "/sponsor",')
        Path(path).write_text(resolved)
        subprocess.run(["git", "add", "--", path], check=True)
    if git("diff", "--name-only", "--diff-filter=U").strip():
        raise SystemExit("Unmerged paths remain")


if __name__ == "__main__":
    main()
