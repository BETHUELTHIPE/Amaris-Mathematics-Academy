"""Generate Prometheus config for a monitoring host separate from Django."""

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit


def https_target(value):
    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
    ):
        raise ValueError("Monitoring application targets must be HTTPS URLs without credentials, queries or fragments.")
    return parts


def build_config(metrics_url, health_url, site_url):
    django = https_target(metrics_url)
    https_target(health_url)
    https_target(site_url)
    jobs = [
        {
            "job_name": "prometheus",
            "metrics_path": "/monitoring/prometheus/metrics",
            "static_configs": [{"targets": ["localhost:9090"]}],
        },
        {
            "job_name": "django",
            "scheme": "https",
            "metrics_path": django.path or "/metrics",
            "static_configs": [{"targets": [django.netloc]}],
        },
        {
            "job_name": "flower",
            "metrics_path": "/monitoring/flower/metrics",
            "basic_auth": {"username_file": "/tmp/flower_username", "password_file": "/tmp/flower_password"},
            "static_configs": [{"targets": ["flower:5555"]}],
        },
        {
            "job_name": "cadvisor",
            "metrics_path": "/monitoring/cadvisor/metrics",
            "static_configs": [{"targets": ["cadvisor:8080"]}],
        },
    ]
    for name, port in (
        ("alertmanager", 9093),
        ("postgres_exporter", 9187),
        ("redis_exporter", 9121),
        ("redis_cache_exporter", 9121),
        ("node_exporter", 9100),
        ("blackbox_exporter", 9115),
    ):
        job = {"job_name": name, "static_configs": [{"targets": [f"{name}:{port}"]}]}
        if name == "alertmanager":
            job["metrics_path"] = "/monitoring/alertmanager/metrics"
        jobs.append(job)
    jobs.append(
        {
            "job_name": "blackbox_http",
            "metrics_path": "/probe",
            "params": {"module": ["http_2xx"]},
            "static_configs": [{"targets": [site_url, health_url]}],
            "relabel_configs": [
                {"source_labels": ["__address__"], "target_label": "__param_target"},
                {"source_labels": ["__param_target"], "target_label": "instance"},
                {"target_label": "__address__", "replacement": "blackbox_exporter:9115"},
            ],
        }
    )
    return {
        "global": {"scrape_interval": "15s", "evaluation_interval": "15s"},
        "alerting": {
            "alertmanagers": [
                {"path_prefix": "/monitoring/alertmanager", "static_configs": [{"targets": ["alertmanager:9093"]}]}
            ]
        },
        "rule_files": ["/etc/prometheus/rules/*.yml"],
        "scrape_configs": jobs,
    }


if __name__ == "__main__":
    config = build_config(
        os.environ["DJANGO_METRICS_URL"], os.environ["DJANGO_HEALTH_URL"], os.environ["PUBLIC_SITE_URL"]
    )
    destination = Path(sys.argv[1])
    destination.write_text(json.dumps(config, indent=2))
    destination.chmod(0o644)
