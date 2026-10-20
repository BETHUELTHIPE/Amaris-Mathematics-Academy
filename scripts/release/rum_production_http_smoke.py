"""Read-only/invalid-request production smoke for the privacy-preserving RUM rollout.

Uses no visitor data or credentials and never sends a valid sample.
It proves runtime feature flags and privacy guards without polluting field p75.
"""
import json
import time
import urllib.error
import urllib.request

BACKEND = "https://amaris-production-web.onrender.com"
FRONTEND = "https://amaris-mathematics-academy-live-students.onrender.com"


def probe(url, *, method="GET", body=None, headers=None, status=200):
    data = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "User-Agent": "Amaris-RUM-release-smoke/1.0",
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if body is not None else {}),
            **(headers or {}),
        },
    )
    for i in range(6):
        try:
            with urllib.request.urlopen(req, timeout=24) as response:
                result, response_headers = response.status, response.headers
                response.read(1200)
        except urllib.error.HTTPError as err:
            result, response_headers = err.code, err.headers
        except (OSError, TimeoutError):
            result, response_headers = 0, {}
        if result == status:
            print(f"PASS HTTP {result} {url[len(BACKEND):] if url.startswith(BACKEND) else url[len(FRONTEND):]}")
            return response_headers
        if i < 5 and result in (0, 502, 503, 504):
            time.sleep(9)
            continue
        raise SystemExit(f"FAIL: expected HTTP {status} but received {result}")
    raise SystemExit("FAIL: HTTP checks exhausted retries")


def main():
    for site, path in [
        (BACKEND, "/health/"),
        (BACKEND, "/health/ready/"),
        (FRONTEND, "/"),
        (FRONTEND, "/announcements"),
    ]:
        probe(site + path)
    bad_token = probe(
        BACKEND + "/api/v1/rum/",
        method="POST",
        body={"records": [{"name": "LCP", "value": 1234,
                           "route": "home", "device": "mobile", "network": "4g"}]},
        headers={"X-Amaris-Rum-Release": "000000000000"},
        status=403,
    )
    assert "no-store" in bad_token.get("Cache-Control", ""), "Uncacheable private receiver required"

    foreign = probe(
        FRONTEND + "/api/field-vitals",
        method="POST",
        headers={"Origin": "https://malicious.invalid"},
        body={"records": []},
        status=403,
    )
    assert "no-store" in foreign.get("Cache-Control", ""), "Bad origins must not be cached"

    invalid = probe(
        FRONTEND + "/api/field-vitals",
        method="POST",
        headers={"Origin": FRONTEND},
        body={"records": [{
            "name": "LCP", "value": 1234, "route": "home",
            "device": "mobile", "network": "4g",
            "email": "not-a-real-address",
        }]},
        status=400,
    )
    assert "no-store" in invalid.get("Cache-Control", ""), "Rejected personal data must not be cached"
    probe(FRONTEND + "/api/field-vitals", status=405)

    # A superuser report cannot be exposed through a public API.
    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(BACKEND + "/admin/content/webvitalbucket/report/")
    try:
        opener.open(req, timeout=24)
    except urllib.error.HTTPError as err:
        if err.code not in (302, 403):
            raise
    else:
        raise SystemExit("FAIL public access to superuser report")
    print("PASS RUM superuser report is not public")
    print("PASS production HTTP RUM privacy and readiness; no synthetic metrics written")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


if __name__ == "__main__":
    main()
