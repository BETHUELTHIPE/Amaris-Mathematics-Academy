"""Render validated Docker gateway and scrape configuration; never print secrets."""

import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit


def https_origin(value: str) -> str:
    if any(character.isspace() or ord(character) < 32 for character in value) or "\\" in value:
        raise ValueError("The HTTPS origin must not contain whitespace or backslashes.")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
        or not re.fullmatch(r"[A-Za-z0-9.-]+", parsed.netloc)
    ):
        raise ValueError("Use an HTTPS origin with a DNS hostname and no path or credentials.")
    return f"https://{parsed.netloc}"


def render(destination: Path) -> None:
    origin = https_origin(os.environ["DJANGO_ORIGIN"])
    domain = os.environ["MONITORING_DOMAIN"]
    https_origin(f"https://{domain}")
    token = Path("/run/secrets/prometheus_api_token").read_text().strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", token):
        raise ValueError("The Prometheus API token must be 43–128 URL-safe random characters.")
    destination.mkdir(parents=True, exist_ok=True)
    template = Path("/config/gateway.conf.template").read_text()
    for key, value in {
        "DJANGO_ORIGIN": origin,
        "DJANGO_HOST": urlsplit(origin).netloc,
        "MONITORING_DOMAIN": domain,
        "API_TOKEN": token,
    }.items():
        template = template.replace("@@" + key + "@@", value)
    (destination / "gateway.conf").write_text(template)
    (destination / "gateway.conf").chmod(0o600)
    config = {
        "global": {"scrape_interval": "15s", "evaluation_interval": "15s"},
        "scrape_configs": [
            {
                "job_name": "prometheus",
                "metrics_path": "/monitoring/prometheus/metrics",
                "static_configs": [{"targets": ["prometheus:9090"]}],
            },
            {
                "job_name": "django",
                "scheme": "https",
                "metrics_path": "/metrics",
                "authorization": {"credentials_file": "/run/secrets/django_metrics_token"},
                "static_configs": [{"targets": [urlsplit(origin).netloc]}],
            },
            {
                "job_name": "flower",
                "metrics_path": "/monitoring/flower/metrics",
                "static_configs": [{"targets": ["flower:5555"]}],
            },
            {
                "job_name": "cadvisor",
                "metrics_path": "/monitoring/cadvisor/metrics",
                "static_configs": [{"targets": ["cadvisor:8080"]}],
            },
        ],
    }
    (destination / "prometheus.json").write_text(json.dumps(config, indent=2) + "\n")


if __name__ == "__main__":
    render(Path("/generated"))
