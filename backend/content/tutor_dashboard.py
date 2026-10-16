"""Tutor-only earnings page: server-rendered, no student PII or bank details."""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.db.models import Count, Max
from django.shortcuts import render

from content.services.tutor_finance import tutor_dashboard_stats
from content.tutor_finance_models import TutorContract, TutorPaymentProfile, TutorEarning, TutorPayout


@login_required(login_url="/tutor/login/")
def tutor_dashboard(request):
    if not request.user.is_active or not TutorContract.objects.filter(tutor=request.user).exists():
        return HttpResponseForbidden("This page is available to contracted tutors only.")
    stats = tutor_dashboard_stats(request.user)
    entries = [
        {"title": "Topical videos paid", "subtitle": "Verified paid video requests", "key": "video"},
        {"title": "Online classes booked", "subtitle": "Verified paid bookings", "key": "live_class"},
        {"title": "Courses sold", "subtitle": "Verified paid course orders", "key": "course"},
    ]
    max_count = max([stats["categories"][item["key"]]["count"] for item in entries] + [1])
    for item in entries:
        item.update(stats["categories"][item["key"]])
        item["bar_width"] = max(0, round(100 * item["count"] / max_count))
    # Tutor status is derived strictly from THIS tutor's verified financial
    # ledger. Do not expose Airflow's API, DAG controls, or other tutors' records.
    own_earnings = TutorEarning.objects.filter(tutor=request.user)
    earning_counts = {
        row["state"]: row["total"]
        for row in own_earnings.values("state").annotate(total=Count("id"))
    }
    payout_counts = {
        row["state"]: row["total"]
        for row in TutorPayout.objects.filter(earning__tutor=request.user)
        .values("state").annotate(total=Count("id"))
    }
    processing = {
        "held": earning_counts.get(TutorEarning.State.HELD, 0),
        "ready": earning_counts.get(TutorEarning.State.READY, 0),
        "paid": earning_counts.get(TutorEarning.State.PAID, 0),
        "reversed": earning_counts.get(TutorEarning.State.REVERSED, 0),
        "payout_pending": payout_counts.get(TutorPayout.State.AWAITING_PROVIDER, 0),
        "payout_processing": payout_counts.get(TutorPayout.State.PROCESSING, 0),
        "payout_failed": payout_counts.get(TutorPayout.State.FAILED, 0),
        "last_updated": own_earnings.aggregate(last=Max("updated_at"))["last"],
    }
    profile = TutorPaymentProfile.objects.filter(tutor=request.user).first()
    return render(
        request,
        "tutor/earnings_dashboard.html",
        {
            "tutor_name": request.user.get_full_name().strip() or request.user.get_username(),
            "stats": stats,
            "processing": processing,
            "entries": entries,
            "bank_mask": (
                ("•••• " + profile.account_last_four) if profile and profile.account_last_four else "Not configured"
            ),
            "bank_status": (
                "Verified"
                if profile and profile.recipient_verified_at and profile.is_active
                else "Pending verification"
            ),
        },
    )
