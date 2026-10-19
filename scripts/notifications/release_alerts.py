"""Credential-safe Amaris deployment and Lighthouse email notifications.

Invoked by trusted default-branch GitHub Actions only. No student, payment,
SMTP credential, or PR-controlled file content is included in emails.
"""
from __future__ import annotations

import argparse
import json
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import getaddresses
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REPOSITORY = "BETHUELTHIPE/Amaris-Mathematics-Academy"
SERVICES = {
    "srv-dapn6b3tqb8s73d3r7n0": "Production Django backend",
    "srv-damn6d2d0e5s73d02j5g": "Production student frontend",
    "srv-dam2iivcgkoc7383tq50": "Staging Django backend",
    "srv-daqf69qd0e5s73ac62n0": "Staging student frontend",
}
TERMINAL_STATUS = {
    "live": "PASSED",
    "deactivated": "PASSED",  # Was live, later superseded.
    "build_failed": "FAILED",
    "pre_deploy_failed": "FAILED",
    "update_failed": "FAILED",
    "canceled": "CANCELLED",
}
MAX_SEEN_PER_SERVICE = 80


def required_configured() -> bool:
    missing = [
        key for key in (
            "AMARIS_NOTIFY_SMTP_USER",
            "AMARIS_NOTIFY_SMTP_APP_PASSWORD",
            "AMARIS_NOTIFY_TO",
        ) if not os.environ.get(key, "").strip()
    ]
    if missing:
        print("SETUP REQUIRED: add protected GitHub environment secrets: " + ", ".join(missing))
        return False
    return True


def recipients(raw: str) -> list[str]:
    result = []
    for _name, address in getaddresses([raw]):
        address = address.strip()
        if not address or "\n" in address or "\r" in address:
            continue
        if "@" not in address or address.startswith("@") or address.endswith("@"):
            raise ValueError("Invalid notification recipient format")
        if address not in result:
            result.append(address)
    if not result:
        raise ValueError("No valid notification recipients")
    return result


def clean(value: object, length: int = 150) -> str:
    return " ".join(str(value or "").split())[:length]


def send_notification(subject: str, body: str, *, dry_run: bool = False) -> None:
    subject = clean(subject, 180)
    if dry_run:
        print("DRY RUN:", subject)
        print(body)
        return
    user = os.environ["AMARIS_NOTIFY_SMTP_USER"].strip()
    password = os.environ["AMARIS_NOTIFY_SMTP_APP_PASSWORD"].replace(" ", "").strip()
    if not password:
        raise ValueError("Empty SMTP app password")
    to = recipients(os.environ["AMARIS_NOTIFY_TO"])
    if "\r" in user or "\n" in user:
        raise ValueError("Invalid SMTP username")
    mail = EmailMessage()
    mail["From"] = user
    mail["To"] = ", ".join(to)
    mail["Subject"] = subject
    mail.set_content(body)
    # GMail STARTTLS. No insecure plaintext fallback.
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=25) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(user, password)
        smtp.send_message(mail)
    print("PASS: sent email notification for", subject)


def api_json(url: str, token: str) -> object:
    request = Request(
        url,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json" if "api.github.com" in url else "application/json",
            "User-Agent": "Amaris-release-notifier/1.0",
        },
    )
    with urlopen(request, timeout=25) as response:
        return json.load(response)


def lighthouse_summary(event: dict, github_token: str, *, fetch=api_json) -> tuple[str, str]:
    run = event.get("workflow_run") or {}
    run_id = int(run.get("id", 0))
    if not run_id:
        raise ValueError("Missing workflow_run ID")
    workflow = clean(run.get("name", "Lighthouse"), 100)
    steps = []
    for page in range(1, 6):
        jobs = fetch(
            f"https://api.github.com/repos/{REPOSITORY}/actions/runs/{run_id}/jobs?"
            + urlencode({"per_page": 100, "page": page}), github_token
        ).get("jobs", [])
        for job in jobs:
            for step in job.get("steps") or []:
                if "lighthouse" in str(step.get("name", "")).lower():
                    steps.append({"name": step.get("name"), "conclusion": step.get("conclusion"),
                                  "job": job.get("name")})
        if len(jobs) < 100:
            break
    values = {s["conclusion"] for s in steps}
    if "failure" in values or "timed_out" in values:
        status = "FAILED"
    elif "cancelled" in values:
        status = "CANCELLED"
    elif "success" in values and not (values & {"failure", "cancelled"}):
        status = "PASSED"
    else:
        status = "NOT RUN"

    pipeline = clean(run.get("conclusion", "unknown")).upper()
    branch = clean(run.get("head_branch", "unknown"))
    sha = clean(run.get("head_sha", ""))[:12]
    url = clean(run.get("html_url", ""), 280)
    outcome = ", ".join(clean(s["name"], 70) + ": " + clean(s["conclusion"]) for s in steps) or "Lighthouse step was not executed"
    subject = f"Amaris Lighthouse {status} | {workflow}"
    body = (
        f"Amaris Mathematics Academy — Lighthouse test result\n\n"
        f"Lighthouse: {status}\n"
        f"Workflow: {workflow}\n"
        f"Overall CI workflow: {pipeline}\n"
        f"Branch: {branch}\n"
        f"Commit: {sha}\n"
        f"Step results: {outcome}\n\n"
        f"Open CI run and test logs: {url}\n\n"
        "Lighthouse CI is a laboratory performance/accessibility test, not real-user p75 LCP/INP/CLS.\n"
    )
    return subject, body


def render_deployment_summary(service_id: str, deploy: dict) -> tuple[str, str]:
    name = SERVICES[service_id]
    status = clean(deploy.get("status"))
    outcome = TERMINAL_STATUS[status]
    if status == "deactivated":
        label = "PASSED (previously live; superseded)"
    else:
        label = outcome
    sha = clean((deploy.get("commit") or {}).get("id"))[:12]
    deploy_id = clean(deploy.get("id"), 80)
    trigger = clean(deploy.get("trigger"), 60)
    finished = clean(deploy.get("finishedAt"), 80)
    url = f"https://dashboard.render.com/web/{service_id}"
    subject = f"Amaris Render {outcome} | {name}"
    body = (
        f"Amaris Mathematics Academy — Render deployment\n\n"
        f"Outcome: {label}\n"
        f"Service: {name}\n"
        f"Deploy status: {status}\n"
        f"Deploy ID: {deploy_id}\n"
        f"Commit: {sha or 'not provided'}\n"
        f"Trigger: {trigger or 'not provided'}\n"
        f"Completed: {finished or 'not provided'} (UTC)\n\n"
        f"Open service deployments and logs: {url}\n"
        "A PASSED status indicates Render marked the deployment live; it does not replace application smoke tests.\n"
    )
    return subject, body


def poll_render(state_path: Path, render_token: str, *, fetch=api_json,
                send=send_notification, dry_run: bool = False) -> dict:
    if not render_token:
        raise ValueError("RENDER_API_KEY missing")
    old = json.loads(state_path.read_text()) if state_path.exists() else {}
    # First successful configuration check seeds historical deployments without
    # sending old notification emails.
    first_run = not state_path.exists()
    current = {"seen": {key: list(ids) for key, ids in (old.get("seen") or {}).items()}}
    total = 0
    for service, name in SERVICES.items():
        response = fetch(
            f"https://api.render.com/v1/services/{service}/deploys?limit=60",
            render_token,
        )
        if not isinstance(response, list):
            raise RuntimeError(f"Unexpected Render deploy response for {name}")
        deployments = [
            item.get("deploy", item) for item in response
            if isinstance(item, dict)
        ]
        terminal = [d for d in deployments if isinstance(d, dict)
                    and d.get("id") and d.get("status") in TERMINAL_STATUS]
        previous = set(current["seen"].get(service, []))
        if first_run:
            current["seen"][service] = [d["id"] for d in terminal][:MAX_SEEN_PER_SERVICE]
            print(f"SEED: {name} — existing deployment history recorded, no historical emails")
            continue
        new = sorted(
            (d for d in terminal if d["id"] not in previous),
            key=lambda d: d.get("finishedAt") or d.get("createdAt") or "",
        )
        for deploy in new:
            subject, body = render_deployment_summary(service, deploy)
            send(subject, body, dry_run=dry_run)
            total += 1
            previous.add(deploy["id"])
        current["seen"][service] = list(previous)[:MAX_SEEN_PER_SERVICE]
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(current, sort_keys=True, indent=2) + "\n")
    print(f"PASS: Render deployment notification check complete; {total} new emails")
    return current


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("lighthouse", "render"))
    parser.add_argument("--event", type=Path)
    parser.add_argument("--state", type=Path, default=Path(".alerts/render-state.json"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if os.environ.get("GITHUB_REPOSITORY") not in (None, REPOSITORY):
        raise RuntimeError("Unexpected GitHub repository; refusing email notifications")
    if not args.dry_run and not required_configured():
        return
    if args.mode == "lighthouse":
        if args.event is None:
            raise ValueError("--event must point to GitHub's workflow_run payload")
        event = json.loads(args.event.read_text())
        run = event.get("workflow_run") or {}
        if run.get("status") != "completed":
            print("SKIP: workflow_run is not completed")
            return
        subject, body = lighthouse_summary(event, os.environ.get("GITHUB_TOKEN", ""))
        send_notification(subject, body, dry_run=args.dry_run)
    else:
        poll_render(args.state, os.environ.get("RENDER_API_KEY", ""), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
