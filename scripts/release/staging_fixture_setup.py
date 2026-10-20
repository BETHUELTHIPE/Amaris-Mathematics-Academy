"""Create real, isolated staging Auth and Django QA identities.

Only callable with an explicit protected staging environment opt-in. No test
payments, email sends, payout operations, schema migrations, or production I/O.
Passwords and access keys come exclusively from protected GitHub staging secrets.
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import smtplib
import ssl
import sys
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

PROJECT = "atyhhjwwxgzeurnwayay"
PRODUCTION = "epkcuseloinygkakxxdu"
SERVICE = "srv-dam2iivcgkoc7383tq50"
WORKSPACE = "tea-csppi8l6l47c73dk9c90"
API = f"https://{PROJECT}.supabase.co"
BACKEND_BRANCH = "ops/staging-known-good-af8709c-20261019"
EXPECTED_STUDENT = "bethuelmoukangwe8@gmail.com"
EXPECTED_TUTOR = "qa-tutor@amaris.test"
EXPECTED_ADMIN = "amaris_staging_qa_admin"


def need(name: str) -> str:
    value = os.environ.get(name, "")
    if not value or "\r" in value or "\n" in value:
        raise RuntimeError("BLOCK: missing protected staging secret " + name)
    return value


def render_json(key: str, endpoint: str) -> object:
    req = Request(
        "https://api.render.com/v1/" + endpoint,
        headers={"Authorization": "Bearer " + key, "Accept": "application/json"},
    )
    with urlopen(req, timeout=25) as response:
        return json.load(response)


def preflight() -> dict:
    if os.environ.get("GITHUB_REPOSITORY") != "BETHUELTHIPE/Amaris-Mathematics-Academy":
        raise RuntimeError("BLOCK: incorrect GitHub repository")
    if os.environ.get("GITHUB_REF") != "refs/heads/test/staging-fixture-setup-20261020":
        raise RuntimeError("BLOCK: incorrect staging-fixture branch")
    if os.environ.get("PAYFAST_MODE") != "sandbox":
        raise RuntimeError("BLOCK: PayFast sandbox-only fixture policy")
    key = need("RENDER_API_KEY")
    service = render_json(key, f"services/{SERVICE}")
    if service.get("id") != SERVICE or service.get("ownerId") != WORKSPACE:
        raise RuntimeError("BLOCK: Render staging service identity changed")
    if service.get("branch") != BACKEND_BRANCH:
        raise RuntimeError("BLOCK: staging release branch changed")
    records = render_json(key, f"services/{SERVICE}/env-vars?limit=100")
    if isinstance(records, dict):
        records = records.get("envVars", records.get("data", []))
    variables = {}
    for row in records:
        item = row.get("envVar", row)
        if isinstance(item, dict) and isinstance(item.get("key"), str):
            variables[item["key"]] = str(item.get("value") or "")
    db = urlsplit(variables.get("DATABASE_URL", ""))
    correct = (
        db.scheme in {"postgres", "postgresql"}
        and db.path == "/postgres"
        and (
            db.hostname == f"db.{PROJECT}.supabase.co"
            or ((db.hostname or "").endswith(".pooler.supabase.com") and PROJECT in (db.username or ""))
        )
    )
    if not correct or variables.get("SUPABASE_PROJECT_REF") != PROJECT:
        raise RuntimeError("BLOCK: database is not the isolated staging project")
    if PRODUCTION in variables.get("DATABASE_URL", ""):
        raise RuntimeError("BLOCK: production database reference detected")
    mode = (variables.get("PAYFAST_MODE") or variables.get("PAYFAST_ENV") or "").lower()
    if mode != "sandbox":
        raise RuntimeError("BLOCK: Render PayFast must be sandbox")
    print("PASS isolated staging Render service, database and PayFast sandbox", flush=True)

    sender = variables.get("DEFAULT_FROM_EMAIL", "").strip().lower()
    login = variables.get("EMAIL_HOST_USER", "").strip().lower()
    smtp_aligned = sender == login == EXPECTED_STUDENT
    print("SMTP_SENDER_MATCHES_STAGING_GMAIL=" + str(smtp_aligned), flush=True)
    print("SMTP_PASSWORD_PRESENT=" + str(bool(variables.get("EMAIL_HOST_PASSWORD"))), flush=True)
    if (
        variables.get("EMAIL_HOST", "").lower() != "smtp.gmail.com"
        or variables.get("EMAIL_PORT") != "587"
        or variables.get("EMAIL_USE_TLS", "").lower() != "true"
        or variables.get("EMAIL_USE_SSL", "").lower() != "false"
    ):
        print("BLOCK SMTP transport configuration does not match Gmail STARTTLS/587", flush=True)
    names = (
        "STAGING_SUPABASE_SERVICE_ROLE_KEY",
        "STAGING_SUPABASE_PUBLISHABLE_KEY",
        "STAGING_TEST_STUDENT_PASSWORD",
        "STAGING_TEST_TUTOR_PASSWORD",
        "STAGING_TEST_SUPERUSER_PASSWORD",
    )
    for name in names:
        print(name + "=" + ("SET" if os.environ.get(name) else "MISSING"), flush=True)
    print("RENDER_STAGING_AUTH_ADMIN_KEY_PRESENT=" + str(bool(
        variables.get("SUPABASE_SERVICE_ROLE_KEY") or variables.get("SUPABASE_SECRET_KEY")
    )), flush=True)
    print("RENDER_STAGING_PUBLISHABLE_KEY_PRESENT=" + str(bool(
        variables.get("SUPABASE_PUBLISHABLE_KEY") or variables.get("SUPABASE_ANON_KEY")
    )), flush=True)
    print("PREFLIGHT_ONLY=YES; NO_USERS_CREATED=YES; NO_EMAIL_SENT=YES", flush=True)
    return variables


def http_json(url: str, headers: dict, body: dict | None = None) -> dict:
    req = Request(
        url,
        method="POST" if body is not None else "GET",
        headers={**headers, "Accept": "application/json", **({"Content-Type": "application/json"} if body is not None else {})},
        data=None if body is None else json.dumps(body).encode("utf-8"),
    )
    try:
        with urlopen(req, timeout=25) as response:
            return json.load(response)
    except HTTPError as exc:
        # Explicitly suppress response bodies: Auth errors sometimes contain PII.
        raise RuntimeError(f"BLOCK: staging Supabase Auth admin operation failed (HTTP {exc.code})") from None



def smtp_auth_only(variables: dict) -> None:
    """Verify exact staging Gmail STARTTLS credentials; NEVER send any message."""
    if os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        raise RuntimeError("BLOCK: SMTP authentication probe requires manual dispatch")
    if os.environ.get("STAGING_FIXTURE_ACTION") != "SMTP_AUTH_ONLY":
        raise RuntimeError("BLOCK: select SMTP_AUTH_ONLY to test SMTP credentials")
    password = need("STAGING_SMTP_PASSWORD")
    if (
        variables.get("EMAIL_HOST", "").lower() != "smtp.gmail.com"
        or str(variables.get("EMAIL_PORT", "")) != "587"
        or str(variables.get("EMAIL_USE_TLS", "")).lower() != "true"
        or str(variables.get("EMAIL_USE_SSL", "")).lower() != "false"
        or variables.get("EMAIL_HOST_USER", "").strip().lower() != EXPECTED_STUDENT
        or variables.get("DEFAULT_FROM_EMAIL", "").strip().lower() != EXPECTED_STUDENT
    ):
        raise RuntimeError("BLOCK: Render staging Gmail STARTTLS settings do not match the approved account")
    deployed_password = variables.get("EMAIL_HOST_PASSWORD", "")
    if not deployed_password or not hmac.compare_digest(password, deployed_password):
        raise RuntimeError("BLOCK: GitHub staging SMTP secret does not match Render staging EMAIL_HOST_PASSWORD")
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=18) as client:
            client.ehlo()
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
            client.login(EXPECTED_STUDENT, password)
    except Exception as exc:
        # Never include provider exception text: some failures can echo credentials.
        raise RuntimeError("BLOCK: Gmail STARTTLS authentication did not pass (" + type(exc).__name__ + ")") from None
    print("PASS STAGING_GMAIL_STARTTLS_AUTHENTICATED=YES; NO_EMAIL_SENT=YES", flush=True)


def execute(variables: dict) -> None:
    if os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        raise RuntimeError("BLOCK: fixture creation requires a manual GitHub workflow dispatch")
    if os.environ.get("STAGING_FIXTURE_ACTION") != "CREATE_STAGING_QA_USERS":
        raise RuntimeError("BLOCK: select CREATE_STAGING_QA_USERS explicitly")
    if os.environ.get("STAGING_FIXTURE_BOOTSTRAP_CONFIRM") != "CREATE_STAGING_QA_USERS":
        raise RuntimeError("BLOCK: fixture creation requires staging environment opt-in")
    # Never fall back to a Render service's privileged key: only the dedicated
    # GitHub staging environment secret is authorized to create Auth identities.
    service_key = need("STAGING_SUPABASE_SERVICE_ROLE_KEY")
    publishable = (
        os.environ.get("STAGING_SUPABASE_PUBLISHABLE_KEY")
        or variables.get("SUPABASE_PUBLISHABLE_KEY")
        or variables.get("SUPABASE_ANON_KEY")
        or ""
    )
    if not service_key or not publishable:
        raise RuntimeError("BLOCK: secure staging Supabase Auth admin/publishable keys not configured")
    student_password = need("STAGING_TEST_STUDENT_PASSWORD")
    tutor_password = need("STAGING_TEST_TUTOR_PASSWORD")
    admin_password = need("STAGING_TEST_SUPERUSER_PASSWORD")
    if any(len(value) < 24 for value in (student_password, tutor_password, admin_password)):
        raise RuntimeError("BLOCK: each protected test password must be at least 24 characters")
    if len({student_password, tutor_password, admin_password}) < 3:
        raise RuntimeError("BLOCK: each test identity needs a distinct secret")
    if not service_key.startswith(("eyJ", "sb_secret_")):
        raise RuntimeError("BLOCK: protected staging Auth admin key is missing or unrecognized")

    # Import Django using ONLY the verified staging configuration. Never import
    # production settings, run migrations, or synchronize a production DB.
    for name, value in variables.items():
        if name.startswith(("GITHUB_", "RUNNER_", "CI", "AWS_SESSION")):
            continue
        os.environ[name] = value
    os.environ["DATABASE_URL"] = variables["DATABASE_URL"]
    os.environ["SUPABASE_PROJECT_REF"] = PROJECT
    os.environ["DJANGO_SECRET_KEY"] = os.environ.get("DJANGO_SECRET_KEY") or "qa-test-runner-temporary-not-used-for-production"
    os.environ["SUPABASE_DATABASE_REQUIRED"] = "true"
    os.environ["DJANGO_SETTINGS_MODULE"] = "amaris_cms.settings"
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
    import django
    django.setup()
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group
    from django.db import connection, transaction
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        if cursor.fetchone()[0] != "postgres":
            raise RuntimeError("BLOCK: unexpected database name")
    User = get_user_model()
    if User.objects.filter(username__in=["amaris_staging_qa_tutor", EXPECTED_ADMIN]).exists():
        raise RuntimeError("BLOCK: QA Django identities already exist; review before resetting")
    print("PASS staging Django ORM and duplicate-identity checks", flush=True)

    headers = {"apikey": service_key, "Authorization": "Bearer " + service_key}
    existing = http_json(API + "/auth/v1/admin/users?page=1&per_page=200", headers)
    emails = {str(u.get("email") or "").lower() for u in existing.get("users", [])}
    if EXPECTED_STUDENT in emails or EXPECTED_TUTOR in emails:
        raise RuntimeError("BLOCK: staging Auth QA identity already exists; manual recovery required")
    for role, email, password in (
        ("student", EXPECTED_STUDENT, student_password),
        ("tutor", EXPECTED_TUTOR, tutor_password),
    ):
        payload = http_json(
            API + "/auth/v1/admin/users", headers,
            {"email": email, "password": password, "email_confirm": True,
             "app_metadata": {"amaris_test_fixture": "staging-only", "fixture_role": role}},
        )
        if not payload.get("id") and not (payload.get("user") or {}).get("id"):
            raise RuntimeError("BLOCK: Auth createUser did not return an ID")
        print("PASS created confirmed staging Supabase " + role + " QA identity (credentials masked)", flush=True)

    with transaction.atomic():
        tutors, _ = Group.objects.get_or_create(name="Tutors")
        tutor = User.objects.create_user(
            username="amaris_staging_qa_tutor",
            email=EXPECTED_TUTOR,
            password=tutor_password,
            is_staff=False,
            is_superuser=False,
        )
        tutor.groups.add(tutors)
        User.objects.create_superuser(
            username=EXPECTED_ADMIN,
            email="qa-admin@amaris.test",
            password=admin_password,
        )
    for email, password in ((EXPECTED_STUDENT, student_password), (EXPECTED_TUTOR, tutor_password)):
        auth = http_json(
            API + "/auth/v1/token?grant_type=password",
            {"apikey": publishable},
            {"email": email, "password": password},
        )
        if not auth.get("access_token"):
            raise RuntimeError("BLOCK: staging password grant failed; check auth settings")
    print("PASS real staging student/tutor password grants, Django Tutors approval and QA superuser", flush=True)
    print("NO_TEST_PAYMENT=YES; NO_EMAIL_SENT=YES; PRODUCTION_UNCHANGED=YES", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--smtp-auth-only", action="store_true")
    arguments = parser.parse_args()
    config = preflight()
    if arguments.execute:
        execute(config)
    elif arguments.smtp_auth_only:
        smtp_auth_only(config)
