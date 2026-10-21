import email, json, time
from email import policy
from pathlib import Path
from django.conf import settings
from content.models import Payment, LiveClassBooking, VideoRequest, Enrollment
from content.payment_models import Invoice
from content.tasks import deliver_transactional_email, deliver_live_class_confirmation, deliver_video_request_notifications

assert settings.EMAIL_BACKEND == "django.core.mail.backends.filebased.EmailBackend"
checkouts = json.loads(Path("/tmp/amaris-all-payfast-bookings.json").read_text())
assert len(checkouts) == 8
models = {"course": Payment, "live": LiveClassBooking, "video": VideoRequest}
for attempt in range(35):
    pending = []
    for item in checkouts:
        model = models["course" if item["kind"].startswith("course") else "live" if item["kind"].startswith("live") else "video"]
        order = model.objects.get(reference=item["reference"])
        expected = "paid" if model is Payment else "confirmed" if model is LiveClassBooking else "queued"
        if order.status != expected or not order.gateway_verified_at or not order.provider_reference:
            pending.append(item["kind"])
    if not pending:
        break
    time.sleep(3)
else:
    raise AssertionError("Genuine provider settlement not verified for: " + ", ".join(pending))
assert Enrollment.objects.count() == 1
invoice_numbers = set()
for item in checkouts:
    model = models["course" if item["kind"].startswith("course") else "live" if item["kind"].startswith("live") else "video"]
    order = model.objects.get(reference=item["reference"])
    number = Invoice.objects.get(payment=order).invoice_number if model is Payment else order.invoice_number
    assert number
    invoice_numbers.add(number)
    print("PASS genuine sandbox wallet and server-validated provider ITN: " + item["kind"], flush=True)
assert len(invoice_numbers) == 8
deliver_transactional_email.run()
deliver_live_class_confirmation.run()
deliver_video_request_notifications.run()
assert not LiveClassBooking.objects.filter(confirmation_sent_at__isnull=True).exists()
assert not VideoRequest.objects.filter(confirmation_sent_at__isnull=True).exists()
attached = set()
for path in Path("/tmp/amaris-staging-mail").glob("*"):
    message = email.message_from_bytes(path.read_bytes(), policy=policy.default)
    assert "sandbox-buyer@example.invalid" in str(message.get("To", ""))
    for part in message.walk():
        name = part.get_filename() or ""
        if name.endswith(".pdf") and part.get_content_type() == "application/pdf":
            raw = part.get_payload(decode=True)
            assert raw and raw.startswith(b"%PDF-")
            attached.add(name[:-4])
assert invoice_numbers <= attached, "Missing generated PDF receipt attachment for one or more service types"
print("PASS eight verified paid-service invoices and PDF attachments in isolated Django file mailbox")
print("NOT VERIFIED external SMTP/Gmail delivery, Supabase private archive, deployed staging checkout or autonomous workers")
