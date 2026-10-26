"""Staging-only QA student password alignment with protected GitHub credentials.

Never use in production, never print secrets, tokens, user records, or emails.
A verified staging test-account must match the protected QA email exactly.
"""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REF = "atyhhjwwxgzeurnwayay"
ORIGIN = f"https://{REF}.supabase.co"
MANAGEMENT = f"https://api.supabase.com/v1/projects/{REF}/api-keys?reveal=true"

def need(name):
    value = os.environ.get(name, "")
    if not value or "\r" in value or "\n" in value:
        raise SystemExit("BLOCK: protected staging secret unavailable: " + name)
    return value

def fetch(url, *, method="GET", data=None, headers=None):
    payload = json.dumps(data).encode() if data is not None else None
    hdrs = {"Accept": "application/json", **(headers or {})}
    if data is not None: hdrs["Content-Type"] = "application/json"
    try:
        with urlopen(Request(url, method=method, data=payload, headers=hdrs), timeout=35) as response:
            return response.status, json.loads(response.read(400000) or b"{}")
    except HTTPError as error:
        return error.code, None
    except (URLError, TimeoutError, ValueError):
        return 0, None

def check_password(pubkey, email, password):
    status, result = fetch(ORIGIN + "/auth/v1/token?grant_type=password", method="POST",
        headers={"apikey": pubkey}, data={"email": email, "password": password})
    if status != 200 or not isinstance(result, dict): return False
    access_token = result.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        return False
    check, user = fetch(ORIGIN + "/auth/v1/user", headers={"apikey": pubkey, "Authorization": "Bearer " + access_token})
    return bool(check == 200 and isinstance(user, dict)
                and str(user.get("email", "")).strip().lower() == email
                and user.get("email_confirmed_at"))

def main():
    if os.getenv("GITHUB_REPOSITORY") != "BETHUELTHIPE/Amaris-Mathematics-Academy" or os.getenv("GITHUB_REF") != "refs/heads/ops/qa-student-auth-recovery-20261026":
        raise SystemExit("BLOCK: non-staging or unexpected branch")
    email = need("STAGING_TEST_STUDENT_EMAIL").strip().lower()
    tutor = need("STAGING_TEST_TUTOR_EMAIL").strip().lower()
    password = need("STAGING_TEST_STUDENT_PASSWORD")
    public = need("STAGING_SUPABASE_PUBLISHABLE_KEY")
    pat = need("SUPABASE_AUTH_MANAGEMENT_TOKEN")
    if "@" not in email or "@" not in tutor or email == tutor or len(password) < 12:
        raise SystemExit("BLOCK: staging QA identity or password policy invalid")
    if not (public.startswith("sb_publishable_") or public.count(".") == 2):
        raise SystemExit("BLOCK: no public staging key")
    if check_password(public, email, password):
        print("PASS: protected staging QA student credential already works; no update needed")
        return

    code, keys = fetch(MANAGEMENT, headers={"Authorization": "Bearer " + pat})
    if code != 200 or not isinstance(keys, list):
        raise SystemExit("BLOCK: staging management access cannot read API keys; use manual password recovery")
    elevated = next((item.get("api_key") for item in keys
                     if isinstance(item, dict) and item.get("name") == "service_role"
                     and isinstance(item.get("api_key"), str)), None)
    if not elevated:
        raise SystemExit("BLOCK: protected staging-only admin key unavailable; manual recovery needed")

    admin_headers = {"apikey": elevated, "Authorization": "Bearer " + elevated}
    code, data = fetch(ORIGIN + "/auth/v1/admin/users?page=1&per_page=100", headers=admin_headers)
    if code != 200 or not isinstance(data, dict):
        raise SystemExit("BLOCK: staging account inspection not permitted")
    users = data.get("users")
    # This is an isolated, two-account QA staging project; fail closed if it has
    # acquired additional accounts instead of risking edits to actual customers.
    if not isinstance(users, list) or len(users) != 2 or not any(
        str(x.get("email", "")).strip().lower() == tutor for x in users if isinstance(x, dict)
    ):
        raise SystemExit("BLOCK: staging user roster differs from dedicated two-account QA fixture")
    matches = [u for u in users if isinstance(u, dict)
               and str(u.get("email", "")).strip().lower() == email]
    if len(matches) != 1:
        raise SystemExit("BLOCK: protected student email does not identify one existing staging user")
    student = matches[0]
    metadata = student.get("app_metadata") or {}
    if (not student.get("email_confirmed_at") or metadata.get("role") in ("admin", "service_role")
            or (student.get("user_metadata") or {}).get("is_tutor") is True):
        raise SystemExit("BLOCK: staging target is not an eligible verified QA student")
    uid = student.get("id")
    if not isinstance(uid, str) or len(uid) != 36:
        raise SystemExit("BLOCK: invalid staging QA account identifier")

    print("PASS: exact protected staging account verified; attempting one controlled password alignment")
    code, updated = fetch(ORIGIN + "/auth/v1/admin/users/" + uid,
                         method="PUT", headers=admin_headers, data={"password": password})
    if code != 200:
        raise SystemExit("BLOCK: staging QA password update was rejected")
    if not check_password(public, email, password):
        raise SystemExit("BLOCK: updated staging QA password did not authenticate")
    print("PASS: recovered staging QA student password works with existing protected GitHub secret")
    print("No user PII, secrets or tokens emitted. Production unchanged.")

if __name__ == "__main__":
    main()
