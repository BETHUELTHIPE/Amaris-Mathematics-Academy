"""CI-only callback observation. Never records payloads, secrets or source addresses."""
import hmac
import ipaddress
import json
from pathlib import Path
from django.utils.deprecation import MiddlewareMixin

class CallbackDiagnostics(MiddlewareMixin):
    def process_request(self, request):
        if request.method != "POST" or request.path != "/api/v1/payfast/itn/":
            return
        from content.payfast_views import _request_ip, _allowed_networks
        from content.services.payments import _payfast_credentials, generate_payfast_signature
        payload = {str(k):str(v) for k,v in request.POST.items()}
        networks = _allowed_networks()
        def allowed(value):
            try: return any(ipaddress.ip_address(value) in network for network in networks)
            except ValueError: return False
        merchant, _, passphrase = _payfast_credentials()
        prefix = str(payload.get("m_payment_id","")).split("-",1)[0]
        request._safe_callback_diagnostic = {
            "kind": {"PF":"course","LCB":"live_class","VRQ":"video"}.get(prefix,"unknown"),
            "source_allowed": allowed(_request_ip(request)),
            "cloudflare_source_allowed": allowed(request.META.get("HTTP_CF_CONNECTING_IP","")),
            "merchant_matches": hmac.compare_digest(str(payload.get("merchant_id","")).strip(), merchant),
            "signature_matches": hmac.compare_digest(str(payload.get("signature","")).strip().lower(), generate_payfast_signature(payload,passphrase)),
            "complete": payload.get("payment_status") == "COMPLETE",
        }
    def process_exception(self, request, exception):
        if hasattr(request,"_safe_callback_diagnostic"):
            request._safe_callback_diagnostic["exception_class"] = type(exception).__name__
    def process_response(self, request, response):
        diagnostic = getattr(request,"_safe_callback_diagnostic",None)
        if diagnostic is not None:
            diagnostic["http_status"] = response.status_code
            data = getattr(response,"data",{})
            safe = {
                "Invalid payment notification source.":"invalid_source",
                "Payment notification source is not trusted.":"untrusted_source",
                "invalid_callback":"invalid_callback", "unknown_payment":"unknown_payment",
                "verification_timeout":"verification_timeout",
                "verification_network_failure":"verification_network_failure",
                "tampered_amount":"tampered_amount", "wrong_student":"wrong_student",
                "wrong_service":"wrong_service",
            }
            diagnostic["disposition"] = safe.get(str(data.get("detail","")),"accepted" if response.status_code == 200 else "other_rejection")
            with Path("/tmp/amaris-safe-callbacks.jsonl").open("a") as stream:
                stream.write(json.dumps(diagnostic,sort_keys=True)+"\n")
        return response
