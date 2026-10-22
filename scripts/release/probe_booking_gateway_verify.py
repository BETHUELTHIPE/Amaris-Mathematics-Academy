import email, json, time
from email import policy
from pathlib import Path
from django.conf import settings
from content.models import Payment, LiveClassBooking, VideoRequest, Enrollment
from content.payment_models import Invoice
from content.payment_models import PaymentWebhookEvent

assert settings.EMAIL_BACKEND == "django.core.mail.backends.filebased.EmailBackend"
checkouts = json.loads(Path("/tmp/amaris-all-payfast-bookings.json").read_text())
assert len(checkouts) == 1
models = {"course": Payment, "live": LiveClassBooking, "video": VideoRequest}
for attempt in range(60):
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
    for item in checkouts:
        model = models["course" if item["kind"].startswith("course") else "live" if item["kind"].startswith("live") else "video"]
        order = model.objects.get(reference=item["reference"])
        print("SAFE_ORDER_STATE=" + json.dumps({"kind":item["kind"],"status":order.status,"verified":bool(order.gateway_verified_at),"provider_reference_present":bool(order.provider_reference)}),flush=True)
    for event in PaymentWebhookEvent.objects.all():
        print("SAFE_COURSE_EVENT=" + json.dumps({"state":event.state,"error_code":event.last_error_code,"attempts":event.attempts}),flush=True)
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
assert len(invoice_numbers) == 1
# Delivery must be performed by the real Celery worker and Beat, never .run().
for attempt in range(60):
    if not LiveClassBooking.objects.filter(confirmation_sent_at__isnull=True).exists() and not VideoRequest.objects.filter(confirmation_sent_at__isnull=True).exists():
        break
    time.sleep(3)
assert not LiveClassBooking.objects.filter(confirmation_sent_at__isnull=True).exists(), "Celery did not deliver all class confirmations"
assert not VideoRequest.objects.filter(confirmation_sent_at__isnull=True).exists(), "Celery did not deliver all video confirmations"
# Wait for Beat to dispatch the course receipt and the worker to write the PDF.
for attempt in range(45):
    if list(Path("/tmp/amaris-staging-mail").glob("*")):
        break
    time.sleep(2)
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
print("PASS one verified course invoice and PDF attachments delivered by autonomous Celery/Beat in isolated file mailbox")
print("NOT VERIFIED external SMTP/Gmail delivery, Supabase private archive, deployed staging checkout or deployed staging workers")
