"""Plan and preflight isolated Django/Celery services; apply only after cost approval.

No web service, database, broker, monitoring service or environment is modified.
Values are copied inside the protected runner and are never included in reports.
"""

import argparse
import json
import os
import sys
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

WORKSPACE = "tea-csppi8l6l47c73dk9c90"
REPO = "https://github.com/BETHUELTHIPE/Amaris-Mathematics-Academy"
PLAN = "0.5c-512mb"
MONTHLY_USD = 21
ENVIRONMENTS = {
    "staging": {
        "web": "srv-dam2iivcgkoc7383tq50",
        "web_name": "amaris-mathematics-academy-staging",
        "branch": "ops/staging-known-good-af8709c-20261019",
        "sha": "1b3b0c532060212578ad7e512dc1f4cf64eb8657",
        "broker": "red-dam2golbedkc73ae6ph0",
        "project": "atyhhjwwxgzeurnwayay",
    },
    "production": {
        "web": "srv-dapn6b3tqb8s73d3r7n0",
        "web_name": "amaris-production-web",
        "branch": "production-release-20260923",
        "sha": "751393e8fdd4eba96cec354b013bb6654431068c",
        "broker": "red-dapaglkja7ms73ajrkq0",
        "project": "epkcuseloinygkakxxdu",
    },
}
ROLES = {
    "critical-worker": "worker --loglevel=INFO --queues=critical,default --concurrency=1 --events",
    "notification-worker": "worker --loglevel=INFO --queues=notifications --concurrency=1 --events",
    "beat": "beat --loglevel=INFO --pidfile=/tmp/celerybeat.pid --schedule=/tmp/celerybeat-schedule",
}
# Explicit allowlist: never copy Render/GitHub tokens, payment merchant secrets or
# arbitrary web configuration into a worker. Keep storage aliases for both releases.
COMMON_KEYS = set("""
DJANGO_SECRET_KEY DATABASE_URL DATABASE_SSL_REQUIRED DATABASE_CONN_MAX_AGE
DATABASE_CONNECT_TIMEOUT DATABASE_STATEMENT_TIMEOUT_MS DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_MS
SUPABASE_DATABASE_REQUIRED SUPABASE_PROJECT_REF SUPABASE_URL SUPABASE_PUBLISHABLE_KEY
SUPABASE_S3_REQUIRED SUPABASE_S3_ENDPOINT_URL SUPABASE_STORAGE_S3_ENDPOINT AWS_S3_ENDPOINT_URL
SUPABASE_S3_ACCESS_KEY_ID SUPABASE_STORAGE_S3_ACCESS_KEY_ID AWS_ACCESS_KEY_ID
SUPABASE_S3_SECRET_ACCESS_KEY SUPABASE_STORAGE_S3_SECRET_ACCESS_KEY AWS_SECRET_ACCESS_KEY
SUPABASE_S3_ADMIN_BUCKET SUPABASE_STORAGE_BUCKET_NAME CMS_STORAGE_BUCKET_NAME
SUPABASE_S3_STUDENT_BUCKET SUPABASE_STUDENT_DOCUMENTS_BUCKET_NAME STUDENT_STORAGE_BUCKET_NAME
SUPABASE_S3_REGION AWS_S3_REGION_NAME AWS_S3_ADDRESSING_STYLE SUPABASE_STORAGE_ENABLED
TUTOR_BANK_FERNET_KEY PUBLIC_SITE_URL PUBLIC_API_URL
""".split())
SMTP_KEYS = set("""
EMAIL_HOST EMAIL_PORT EMAIL_HOST_USER EMAIL_HOST_PASSWORD EMAIL_USE_TLS EMAIL_USE_SSL
EMAIL_TIMEOUT_SECONDS DEFAULT_FROM_EMAIL SERVER_EMAIL GMAIL_USER GMAIL_EMAIL GMAIL_APP_PASSWORD
""".split())


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class RenderAPI:
    def __init__(self, token, allow_create=False):
        if not token:
            raise ValueError("Protected RENDER_API_KEY is unavailable")
        self.token = token
        self.allow_create = allow_create
        self.opener = build_opener(NoRedirect)

    def request(self, method, path, payload=None):
        if not path.startswith("/") or ".." in path:
            raise ValueError("Invalid Render API path")
        if method != "GET" and not (self.allow_create and method == "POST" and path == "/services"):
            raise ValueError("Only explicitly approved worker creation is allowed")
        request = Request(
            "https://api.render.com/v1" + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
            method=method,
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as exc:
            raise RuntimeError(f"Render {method} failed: HTTP {exc.code}; response suppressed") from None
        except (OSError, ValueError):
            raise RuntimeError(f"Render {method} failed; response suppressed") from None


def rows(api, path):
    cursor = ""
    seen = set()
    result = []
    for _ in range(100):
        separator = "&" if "?" in path else "?"
        page = api.request("GET", path + separator + urlencode({"limit": 100, "cursor": cursor}))
        result.extend(page)
        if len(page) < 100:
            return result
        cursor = page[-1].get("cursor")
        if not cursor or cursor in seen:
            raise ValueError("Incomplete Render pagination")
        seen.add(cursor)
    raise ValueError("Render pagination exceeded bounded read")


def env_values(api, service_id):
    values = {}
    for row in rows(api, f"/services/{service_id}/env-vars"):
        var = row.get("envVar", row)
        if var["key"] in values:
            raise ValueError("Duplicate environment variable; resolve before provisioning")
        values[var["key"]] = var.get("value", "")
    return values


def truth(value):
    return str(value).lower() in {"true", "1", "yes", "on"}


def broker_host(value):
    parsed = urlsplit(value)
    if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
        raise ValueError("Explicit Redis/Valkey broker URL required")
    return parsed.hostname


def validate_bindings(environment, values):
    spec = ENVIRONMENTS[environment]
    project = spec["project"]
    required = ("DJANGO_SECRET_KEY", "DATABASE_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND")
    if any(not values.get(key) for key in required):
        raise ValueError("Missing required Django/database/Celery configuration")
    parsed = urlsplit(values["DATABASE_URL"])
    direct = parsed.hostname == f"db.{project}.supabase.co" and parsed.username == "postgres"
    pooled = (parsed.hostname or "").endswith(".pooler.supabase.com") and parsed.username == f"postgres.{project}"
    if parsed.scheme not in {"postgres", "postgresql"} or not (direct or pooled):
        raise ValueError("Database does not match the intended environment")
    if values.get("SUPABASE_URL", "").rstrip("/") != f"https://{project}.supabase.co":
        raise ValueError("Auth project does not match the intended environment")
    if values.get("SUPABASE_PROJECT_REF") != project or not truth(values.get("DATABASE_SSL_REQUIRED")):
        raise ValueError("Project/SSL safeguards are missing")
    for key in ("CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"):
        if broker_host(values[key]).split(".")[0] != spec["broker"]:
            raise ValueError("Celery does not use the expected isolated broker")
    endpoint = values.get("SUPABASE_S3_ENDPOINT_URL") or values.get("SUPABASE_STORAGE_S3_ENDPOINT") or values.get("AWS_S3_ENDPOINT_URL", "")
    if urlsplit(endpoint).hostname != f"{project}.storage.supabase.co":
        raise ValueError("Private storage endpoint does not match the intended environment")
    groups = (
        ("SUPABASE_S3_ACCESS_KEY_ID", "SUPABASE_STORAGE_S3_ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID"),
        ("SUPABASE_S3_SECRET_ACCESS_KEY", "SUPABASE_STORAGE_S3_SECRET_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY"),
        ("SUPABASE_S3_ADMIN_BUCKET", "SUPABASE_STORAGE_BUCKET_NAME", "CMS_STORAGE_BUCKET_NAME"),
        ("SUPABASE_S3_STUDENT_BUCKET", "SUPABASE_STUDENT_DOCUMENTS_BUCKET_NAME", "STUDENT_STORAGE_BUCKET_NAME"),
    )
    if any(not any(values.get(k) for k in group) for group in groups):
        raise ValueError("Private invoice storage bindings are incomplete")
    if environment == "staging" and (values.get("PAYFAST_MODE") or values.get("PAYFAST_ENV", "")).lower() != "sandbox":
        raise ValueError("Staging must remain PayFast sandbox")
    user = values.get("EMAIL_HOST_USER") or values.get("GMAIL_USER") or values.get("GMAIL_EMAIL")
    password = values.get("EMAIL_HOST_PASSWORD") or values.get("GMAIL_APP_PASSWORD")
    sender = values.get("DEFAULT_FROM_EMAIL", "")
    checks = {
        "EMAIL_HOST": bool(values.get("EMAIL_HOST")),
        "EMAIL_HOST_USER (or Gmail alias)": bool(user),
        "EMAIL_HOST_PASSWORD (or Gmail alias)": bool(password),
        "DEFAULT_FROM_EMAIL (real sender)": "@" in sender and ".invalid" not in sender,
    }
    missing = [key for key, valid in checks.items() if not valid]
    if missing:
        raise ValueError("Missing SMTP requirements: " + ", ".join(missing))
    tls, ssl = truth(values.get("EMAIL_USE_TLS", "true")), truth(values.get("EMAIL_USE_SSL", "false"))
    if tls == ssl:
        raise ValueError("Exactly one SMTP TLS or SSL transport must be enabled")


def payload(environment, role, source_values):
    spec = ENVIRONMENTS[environment]
    name = f"amaris-{environment}-{role}"
    command = "celery -A amaris_cms " + ROLES[role]
    if role != "beat":
        command += f" --hostname={environment}-{role}@%h"
    keys = COMMON_KEYS | (SMTP_KEYS if role == "notification-worker" else set())
    values = {k: v for k, v in source_values.items() if k in keys}
    values.update({
        "PYTHON_VERSION": "3.13.15", "DJANGO_DEBUG": "false",
        "SERVICE_ROLE": "celery-" + role, "CELERY_BROKER_URL": source_values["CELERY_BROKER_URL"],
        "CELERY_RESULT_BACKEND": source_values["CELERY_RESULT_BACKEND"],
    })
    if role == "notification-worker":
        values["EMAIL_BACKEND"] = "django.core.mail.backends.smtp.EmailBackend"
    return {
        "type": "background_worker", "name": name, "ownerId": WORKSPACE,
        "repo": REPO, "branch": spec["branch"], "autoDeployTrigger": "off",
        "serviceDetails": {
            "runtime": "python", "plan": PLAN, "region": "frankfurt", "numInstances": 1,
            "maxShutdownDelaySeconds": 120,
            "envSpecificDetails": {
                "buildCommand": f'test "$RENDER_GIT_COMMIT" = "{spec["sha"]}" && cd backend && pip install -r requirements.txt && python manage.py check --deploy --fail-level ERROR',
                "startCommand": "cd backend && exec " + command,
            },
        },
        "envVars": [{"key": k, "value": v} for k, v in sorted(values.items())],
    }


def validate_existing(service, expected):
    for key in ("type", "name", "ownerId", "branch", "autoDeployTrigger"):
        if service.get(key) != expected[key]:
            raise ValueError("Existing worker differs from reviewed plan")
    if service.get("repo", "").removesuffix(".git") != REPO or service.get("suspended") != "not_suspended":
        raise ValueError("Existing worker has unexpected source or state")
    actual = service["serviceDetails"]
    wanted = expected["serviceDetails"]
    if actual.get("plan") not in {PLAN, "starter"}:
        raise ValueError("Existing worker compute differs from budget")
    for key in ("runtime", "region", "numInstances", "maxShutdownDelaySeconds", "envSpecificDetails"):
        if actual.get(key) != wanted[key]:
            raise ValueError("Existing worker commands or singleton settings differ")


def preflight(api, environment):
    spec = ENVIRONMENTS[environment]
    source = api.request("GET", f'/services/{spec["web"]}')
    if any(source.get(k) != v for k, v in {
        "id": spec["web"], "name": spec["web_name"], "ownerId": WORKSPACE,
        "type": "web_service", "branch": spec["branch"], "suspended": "not_suspended",
    }.items()) or source.get("repo", "").removesuffix(".git") != REPO or source["serviceDetails"].get("region") != "frankfurt":
        raise ValueError("Django web source differs from the reviewed environment")
    deploys = rows(api, f'/services/{spec["web"]}/deploys')
    live = [r.get("deploy", r) for r in deploys if r.get("deploy", r).get("status") == "live"]
    pending = {"created", "build_in_progress", "pre_deploy_in_progress", "update_in_progress", "queued"}
    if any(r.get("deploy", r).get("status") in pending for r in deploys) or not live or live[0].get("commit", {}).get("id") != spec["sha"]:
        raise ValueError("Django release changed or a deploy is in progress; review source pin")
    broker = api.request("GET", f'/key-value/{spec["broker"]}')
    if broker.get("owner", {}).get("id") != WORKSPACE or broker.get("region") != "frankfurt" or broker.get("name") != f"amaris-{environment}-broker" or broker.get("options", {}).get("maxmemoryPolicy") != "noeviction":
        raise ValueError("Unexpected broker identity or queue eviction policy")
    values = env_values(api, spec["web"])
    validate_bindings(environment, values)
    definitions = [payload(environment, role, values) for role in ROLES]
    services = [r.get("service", r) for r in rows(api, "/services?ownerId=" + WORKSPACE)]
    existing = {}
    for service in services:
        if service.get("name") in {d["name"] for d in definitions}:
            if service["name"] in existing:
                raise ValueError("Duplicate Celery service name")
            existing[service["name"]] = service
        elif service.get("type") == "background_worker" and service.get("suspended") == "not_suspended" and service.get("repo", "").removesuffix(".git") == REPO:
            details = service.get("serviceDetails", {}).get("envSpecificDetails", {})
            command = details.get("startCommand") or details.get("dockerCommand", "")
            # Monitoring consumes its own queue and is intentionally untouched.
            if "celery" in command and "monitoring-verification" not in command:
                other = env_values(api, service["id"])
                if broker_host(other.get("CELERY_BROKER_URL", "")) == broker_host(values["CELERY_BROKER_URL"]):
                    raise ValueError("Unmanaged worker/scheduler already uses this broker")
    for definition in definitions:
        if definition["name"] in existing:
            service = existing[definition["name"]]
            validate_existing(service, definition)
            actual_env = env_values(api, service["id"])
            wanted_env = {v["key"]: v["value"] for v in definition["envVars"]}
            if actual_env != wanted_env:
                raise ValueError("Existing worker environment differs; refusing silent update")
    return definitions, existing


def provision(api, environment, apply=False, approved_monthly_usd=None):
    if apply and approved_monthly_usd != MONTHLY_USD:
        raise ValueError("Explicit additional US$21/month approval per environment is required")
    definitions, existing = preflight(api, environment)
    report = []
    for definition in definitions:
        name = definition["name"]
        if name in existing:
            report.append({"name": name, "action": "retained", "serviceId": existing[name]["id"]})
        elif not apply:
            report.append({"name": name, "action": "would-create", "plan": PLAN})
        else:
            result = api.request("POST", "/services", definition)
            service = result["service"]
            validate_existing(service, definition)
            entry = {"name": name, "action": "created", "serviceId": service["id"], "deployId": result.get("deployId")}
            report.append(entry)
            # Persist non-secret IDs even if a later creation fails. Retry adopts them.
            print(json.dumps(entry), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", choices=ENVIRONMENTS, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--approved-monthly-usd", type=int)
    args = parser.parse_args()
    if args.apply and args.approved_monthly_usd != MONTHLY_USD:
        parser.error("Apply requires separate US$21/month approval for this environment")
    if not (args.preflight or args.apply):
        spec = ENVIRONMENTS[args.environment]
        print(json.dumps({"environment": args.environment, "source_sha": spec["sha"],
            "additional_monthly_usd_estimate": MONTHLY_USD, "excludes": "tax and usage",
            "services": [f"amaris-{args.environment}-{r}" for r in ROLES],
            "status": "PLAN ONLY; not provisioned"}, indent=2))
        return
    api = RenderAPI(os.getenv("RENDER_API_KEY"), allow_create=args.apply)
    print(json.dumps(provision(api, args.environment, args.apply, args.approved_monthly_usd), indent=2))
    print("Deployment processing and real SMTP receipt acceptance: NOT VERIFIED")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError) as exc:
        print("BLOCKED: " + str(exc), file=sys.stderr)
        sys.exit(1)
