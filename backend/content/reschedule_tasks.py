from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from content.models import LiveClassBooking, SiteSettings

@shared_task(bind=True, autoretry_for=(OSError,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def notify_reschedule(self, booking_id, previous_start, changed_by, reason):
    booking = LiveClassBooking.objects.select_related("slot", "slot__tutor", "student").get(pk=booking_id)
    admin = SiteSettings.objects.first()
    recipients = sorted(set(filter(None, [booking.student.email, booking.slot.tutor.email, admin.email if admin else ""])))
    if not recipients:
        raise ValueError("No booking recipients configured")
    body = (
        f"Booking: {booking.reference}\n"
        f"Changed by: {changed_by}\n"
        f"Previous start: {previous_start}\n"
        f"New start (UTC): {booking.slot.starts_at.isoformat()}\n"
        f"New end (UTC): {booking.slot.ends_at.isoformat()}\n"
        f"Tutor: {booking.slot.tutor_display_name}\n"
        f"Reason: {reason}\n"
        "Your original payment and invoice remain valid. Use the booking dashboard for current Zoom details."
    )
    for recipient in recipients:
        sent = send_mail("Amaris online lesson rescheduled", body, settings.DEFAULT_FROM_EMAIL, [recipient], fail_silently=False)
        if sent != 1:
            raise OSError("SMTP did not accept reschedule notification")
