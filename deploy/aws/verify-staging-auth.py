"""Configure and test Auth against the dedicated Amazon EC2 staging origin."""

import hashlib
import ipaddress
import json
import os
import sys
import urllib.error
import urllib.request

PROJECT = "atyhhjwwxgzeurnwayay"
AUTH_CONFIG = f"https://api.supabase.com/v1/projects/{PROJECT}/config/auth"
APPROVED_STUDENT_EMAIL_SHA256 = "dff017c2f812483ad01fbb1988d70e420ffd574b53b88c51a1c97d6a4f314d8d"


class VerificationError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(NoRedirect())


def json_request(url, *, headers=None, method="GET", data=None):
    headers = {"Accept": "application/json", **(headers or {})}
    if data is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(data).encode()
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with OPENER.open(request, timeout=25) as response:
        return json.load(response), response.headers


def configure_callbacks(origin, token):
    headers = {"Authorization": f"Bearer {token}"}
    config, _ = json_request(AUTH_CONFIG, headers=headers)
    if config.get("mailer_autoconfirm") is not False or config.get("mailer_allow_unverified_email_sign_ins") is True:
        raise VerificationError("Staging Auth does not enforce verified email.")
    existing = config.get("uri_allow_list") or ""
    if not isinstance(existing, str):
        raise VerificationError("Unexpected Supabase Auth redirect configuration.")
    callbacks = {
        f"{origin}/auth/confirm",
        f"{origin}/auth/confirm?next=**",
        f"{origin}/auth/callback",
        f"{origin}/auth/callback?next=**",
        f"{origin}/reset-password/verify",
    }
    entries = {entry.strip() for entry in existing.split(",") if entry.strip()}
    if missing := callbacks - entries:
        updated = ",".join(filter(None, (existing, ",".join(sorted(missing)))))
        json_request(AUTH_CONFIG, headers=headers, method="PATCH", data={"uri_allow_list": updated})
    verified, _ = json_request(AUTH_CONFIG, headers=headers)
    if not callbacks <= {entry.strip() for entry in (verified.get("uri_allow_list") or "").split(",")}:
        raise VerificationError("Staging Auth callbacks could not be verified.")
    print("The AWS staging HTTPS callbacks are registered and email verification is required.")


def verify_student(origin, email, password, publishable_key):
    if hashlib.sha256(email.encode()).hexdigest() != APPROVED_STUDENT_EMAIL_SHA256:
        raise VerificationError("The configured staging test account does not match the approved identity.")
    session, _ = json_request(
        f"https://{PROJECT}.supabase.co/auth/v1/token?grant_type=password",
        headers={"apikey": publishable_key}, method="POST", data={"email": email, "password": password},
    )
    user = session.get("user") or {}
    if str(user.get("email", "")).lower() != email or not user.get("email_confirmed_at") or not session.get("access_token"):
        raise VerificationError("Staging did not authenticate the verified test student.")
    payload, headers = json_request(
        f"{origin}/api/v1/student/courses/", headers={"Authorization": f"Bearer {session['access_token']}"},
    )
    cache = headers.get("Cache-Control", "").lower()
    if not isinstance(payload, list) or "public" in cache:
        raise VerificationError("The AWS staging dashboard did not return private student data correctly.")
    print("The approved staging test student authenticated and accessed private course data from the AWS dashboard API.")


def main():
    address = ipaddress.IPv4Address(os.environ["STAGING_ADDRESS"])
    if not address.is_global:
        raise SystemExit("AWS staging requires a public HTTPS origin.")
    origin = f"https://{address}"
    token = os.environ.get("SUPABASE_AUTH_MANAGEMENT_TOKEN", "")
    email = os.environ.get("STAGING_TEST_STUDENT_EMAIL", "").strip().lower()
    password = os.environ.get("STAGING_TEST_STUDENT_PASSWORD", "")
    publishable_key = os.environ.get("STAGING_SUPABASE_PUBLISHABLE_KEY", "")
    failures = []
    for label, function, args in (
        ("Auth callbacks", configure_callbacks, (origin, token)),
        ("Test student sign-in", verify_student, (origin, email, password, publishable_key)),
    ):
        if not all(args):
            failures.append(f"{label} could not be verified because protected staging configuration was missing.")
            continue
        try:
            function(*args)
        except urllib.error.HTTPError as error:
            failures.append(f"{label} returned HTTP {error.code}.")
        except VerificationError as error:
            failures.append(f"{label}. {error}")
        except urllib.error.URLError as error:
            failures.append(f"{label} could not connect ({type(error.reason).__name__}).")
        except (TimeoutError, ValueError) as error:
            failures.append(f"{label} failed ({type(error).__name__}).")
    if failures:
        sys.exit("\n".join(failures))


if __name__ == "__main__":
    main()
