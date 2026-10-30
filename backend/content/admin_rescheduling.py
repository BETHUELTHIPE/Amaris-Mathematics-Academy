from datetime import timedelta
from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from content.models import LiveClassBooking, TutorAvailabilitySlot
from content.reschedule_views import move_booking

class AdminRescheduleForm(forms.Form):
    slot = forms.ModelChoiceField(queryset=TutorAvailabilitySlot.objects.none(), label="New available session")
    reason = forms.CharField(required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, booking, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slot"].queryset = TutorAvailabilitySlot.objects.filter(
            tutor=booking.slot.tutor, programme=booking.programme,
            subject=booking.subject, level=booking.level,
            is_active=True, starts_at__gt=timezone.now() + timedelta(hours=24),
        ).exclude(pk=booking.slot_id).order_by("starts_at")

def admin_reschedule_view(model_admin, request, object_id):
    if not request.user.is_staff or not model_admin.has_change_permission(request):
        raise PermissionDenied
    booking = model_admin.get_object(request, object_id)
    if not booking:
        raise Http404("Booking not found")
    form = AdminRescheduleForm(request.POST if request.method == "POST" else None, booking=booking)
    if request.method == "POST" and form.is_valid():
        outcome = move_booking(reference=booking.reference, new_slot_id=form.cleaned_data["slot"].pk,
                               actor="admin", actor_id=request.user.pk, reason=form.cleaned_data["reason"])
        if outcome.status_code == 200:
            model_admin.message_user(request, "Booking rescheduled; email notifications queued.", messages.SUCCESS)
            return redirect(reverse("admin:content_liveclassbooking_change", args=[booking.pk]))
        model_admin.message_user(request, str(outcome.data.get("detail", "Unable to reschedule.")), messages.ERROR)
    return render(request, "admin/content/liveclassbooking/reschedule.html", {
        **model_admin.admin_site.each_context(request), "title": "Reschedule live class",
        "booking": booking, "form": form, "opts": model_admin.model._meta,
    })
