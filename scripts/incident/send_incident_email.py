#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from string import Template
from typing import Any


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _load_template(name: str) -> Template:
    path = Path(__file__).with_name("templates") / name
    return Template(path.read_text(encoding="utf-8"))


def _safe(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _context(incident: dict[str, Any]) -> dict[str, str]:
    event = incident.get("event") if isinstance(incident.get("event"), dict) else {}
    frames = event.get("frames") if isinstance(event.get("frames"), list) else []
    frame_lines = []
    for frame in frames[:8]:
        if not isinstance(frame, dict):
            continue
        frame_lines.append(
            f"{frame.get('file', '')}:{frame.get('line', '')} "
            f"{frame.get('function', '')}"
        )

    return {
        "company_name": _safe(_env("INCIDENT_COMPANY_NAME", "Amaris Mathematics Academy")),
        "company_logo_url": _safe(_env("INCIDENT_COMPANY_LOGO_URL")),
        "company_phone": _safe(_env("INCIDENT_COMPANY_PHONE")),
        "company_email": _safe(_env("INCIDENT_COMPANY_EMAIL")),
        "company_website": _safe(_env("INCIDENT_COMPANY_WEBSITE")),
        "company_address": _safe(_env("INCIDENT_COMPANY_ADDRESS")),
        "fingerprint": _safe(incident.get("fingerprint")),
        "severity": _safe(incident.get("severity")),
        "environment": _safe(incident.get("environment")),
        "source": _safe(incident.get("source")),
        "release_sha": _safe(incident.get("release_sha")),
        "occurred_at": _safe(incident.get("occurred_at")),
        "status_code": _safe(event.get("status_code")),
        "method": _safe(event.get("method")),
        "path": _safe(event.get("path")),
        "correlation_reference": _safe(event.get("correlation_reference")),
        "exception_type": _safe(event.get("exception_type")),
        "frames": _safe("\n".join(frame_lines) or "No stack-frame metadata supplied."),
        "issue_url": _safe(_env("INCIDENT_ISSUE_URL")),
    }


def render(incident: dict[str, Any]) -> tuple[str, str, str]:
    context = _context(incident)
    subject = (
        f"[Amaris production incident] {incident.get('fingerprint', 'unknown')} "
        f"{incident.get('severity', 'error')}"
    )
    text_body = _load_template("production_incident.txt").safe_substitute(context)
    html_body = _load_template("production_incident.html").safe_substitute(context)
    return subject, text_body, html_body


def send(subject: str, text_body: str, html_body: str) -> None:
    host = _env("INCIDENT_SMTP_HOST")
    username = _env("INCIDENT_SMTP_USERNAME")
    password = os.getenv("INCIDENT_SMTP_PASSWORD", "")
    recipient = _env("INCIDENT_EMAIL_TO")
    sender = _env("INCIDENT_EMAIL_FROM") or username
    port = int(_env("INCIDENT_SMTP_PORT", "587"))

    if not all([host, username, password, recipient, sender]):
        raise RuntimeError(
            "Incident email requires SMTP host, username, password, sender, and recipient."
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=20) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(username, password)
        smtp.send_message(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("incident", type=Path)
    parser.add_argument("--render-only", type=Path)
    args = parser.parse_args()

    incident = json.loads(args.incident.read_text(encoding="utf-8"))
    subject, text_body, html_body = render(incident)

    if args.render_only:
        args.render_only.parent.mkdir(parents=True, exist_ok=True)
        args.render_only.write_text(html_body, encoding="utf-8")
        return 0

    send(subject, text_body, html_body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
