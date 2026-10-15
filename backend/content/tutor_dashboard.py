"""Tutor-only earnings page: server-rendered, no student PII or bank details."""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.db.models import Sum

from content.tutor_finance_models import TutorContract, TutorEarning, TutorPaymentProfile
from content.services.tutor_finance import tutor_dashboard_stats


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
    profile = TutorPaymentProfile.objects.filter(tutor=request.user).first()
    return render(
        request,
        "tutor/earnings_dashboard.html",
        {
            "tutor_name": request.user.get_full_name().strip() or request.user.get_username(),
            "stats": stats,
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
