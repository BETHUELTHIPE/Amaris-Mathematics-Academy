"""Safe persisted outcome diagnostics; no raw payloads, credentials or addresses."""
import email
import json
from email import policy
from pathlib import Path
from content.models import Payment, LiveClassBooking, VideoRequest
from content.payment_models import Invoice

path = Path("/tmp/amaris-all-payfast-bookings.json")
if path.exists():
    attached = set()
    for file in Path("/tmp/amaris-staging-mail").glob("*"):
        message = email.message_from_bytes(file.read_bytes(),policy=policy.default)
        for part in message.walk():
            name = part.get_filename() or ""
            body = part.get_payload(decode=True)
            if name.endswith(".pdf") and part.get_content_type()=="application/pdf" and body and body.startswith(b"%PDF-"):
                attached.add(name[:-4])
    verified = 0
    receipts = 0
    for item in json.loads(path.read_text()):
        model = Payment if item["kind"].startswith("course") else LiveClassBooking if item["kind"].startswith("live") else VideoRequest
        order = model.objects.get(reference=item["reference"])
        expected = "paid" if model is Payment else "confirmed" if model is LiveClassBooking else "queued"
        paid = order.status==expected and bool(order.gateway_verified_at and order.provider_reference)
        invoice = Invoice.objects.filter(payment=order).first() if model is Payment else None
        number = (invoice.invoice_number if invoice else "") if model is Payment else order.invoice_number
        pdf = bool(paid and number and number in attached)
        verified += int(paid)
        receipts += int(pdf)
        print("SAFE_PERSISTED_ORDER="+json.dumps({"kind":item["kind"],"status":order.status,"gateway_verified":bool(order.gateway_verified_at),"provider_reference_present":bool(order.provider_reference),"pdf_receipt_present":pdf}),flush=True)
    print("PERSISTED_VERIFIED_ORDERS="+str(verified))
    print("MATCHING_GENERATED_PDF_RECEIPTS="+str(receipts))
else:
    print("PERSISTED_ORDER_DIAGNOSTICS=NOT_AVAILABLE")
