"""Read-only anonymous checks of LIVE student/payment boundaries.

No cookies, Google credentials, PayFast ITNs, student data, payments,
invoice objects or SMTP calls are ever created. This is NOT an E2E paid test.
"""
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, build_opener, Request

FRONT = "https://amaris-mathematics-academy-live-students.onrender.com"
BACK = "https://amaris-production-web.onrender.com"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


opener = build_opener(NoRedirect())


def probe(base, path, allowed, *, allow_login_redirect=False, text=None):
    req = Request(base + path, headers={"User-Agent": "Amaris-release-readonly-privacy/1.0"})
    try:
        response = opener.open(req, timeout=40)
        status, headers = response.status, response.headers
        content = response.read(75000) if text else b""
    except HTTPError as ex:
        status, headers = ex.code, ex.headers
        content = ex.read(75000) if text else b""
    except URLError as ex:
        raise RuntimeError(f"unreachable: {path}: {type(ex).__name__}") from ex

    if status not in allowed:
        raise AssertionError(f"{path}: expected {allowed}, got HTTP {status}")
    if allow_login_redirect:
        loc = headers.get("Location", "")
        parsed = urlparse(loc)
        if parsed.netloc and parsed.netloc != urlparse(FRONT).netloc:
            raise AssertionError(f"{path}: external redirect")
        if "/login" not in parsed.path and "/verify-email" not in parsed.path:
            raise AssertionError(f"{path}: did not protect anonymous access")
    if text and text.lower().encode() not in content.lower():
        raise AssertionError(f"{path}: missing public sign-in option")
    print(f"PASS {path}: HTTP {status} ({'protected' if allow_login_redirect else 'public/read-only'})", flush=True)


def main():
    probe(BACK, "/health/ready/", {200})
    probe(FRONT, "/login", {200})
    probe(FRONT, "/register", {200})
    probe(FRONT, "/dashboard/orders", {302, 303, 307, 308}, allow_login_redirect=True)
    probe(FRONT, "/dashboard/orders/invoice?reference=PF-CI-NOT-A-PAYMENT", {302, 303, 307, 308}, allow_login_redirect=True)
    probe(BACK, "/api/v1/student/orders/", {401, 403})
    probe(BACK, "/api/v1/student/orders/PF-CI-NOT-A-PAYMENT/invoice/", {401, 403})
    probe(BACK, "/api/v1/student/live-classes/bookings/LCB-CI-NOT-A-BOOKING/invoice/", {401, 403})
    print("PASS live anonymous Google/payment/invoice privacy probe. No transaction or login was attempted.", flush=True)


if __name__ == "__main__":
    main()
