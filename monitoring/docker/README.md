# Amaris Docker monitoring stack

This profile runs the monitoring tools as Docker containers on a Linux host. The Amaris application and Supabase/Render database services remain where they are.

## Containers

- Prometheus v3.15.0
- Grafana 13.2.4
- Flower 2.0.1 in a Python 3.13 image
- cAdvisor v0.60.6
- Blackbox Exporter v0.28.0 as the HTTP probe helper for the public Render frontend/backend

Prometheus and Grafana use named Docker volumes. Flower uses a named volume for its local state.

## Security defaults

Prometheus, Grafana, Flower, and cAdvisor bind only to 127.0.0.1 on the Docker host. They are not public by default. Use an SSH tunnel or a separately secured reverse proxy when access is required.

Copy .env.example to .env and set a strong Grafana password. Never commit the real .env.

## Start

```bash
cd monitoring/docker
cp .env.example .env
# edit .env securely
docker compose pull
docker compose build flower
docker compose config
docker compose up -d
docker compose ps
```

Local host endpoints:

- Grafana: http://127.0.0.1:3000
- Prometheus: http://127.0.0.1:9090
- Flower: http://127.0.0.1:5555
- cAdvisor: http://127.0.0.1:8080

## What cAdvisor measures

cAdvisor measures only containers running on this Docker host. It does not expose CPU or memory for Render-managed containers. The Prometheus target is labeled source=monitoring-host so Grafana does not misrepresent those metrics as Render host metrics.

## Flower requirement

Flower needs network access to the same Celery broker used by the Amaris workers. Put the broker URL only in the host's private .env file. If the production broker is not externally reachable, leave Flower stopped or provide a secure private connection; do not expose the broker publicly just to make Flower work.

## Render monitoring

The stack probes:

- https://amaris-mathematics-academy-live-students.onrender.com/
- https://amaris-production-web.onrender.com/health/ready/

It also attempts to scrape the backend's existing /metrics endpoint. If that endpoint is intentionally protected, Prometheus will show that scrape target as down until secure scrape authentication is configured.

## Alerts

prometheus/alerts.yml contains 14 rules covering frontend/backend availability, latency, TLS expiry, scrape health, monitoring-host container pressure, OOM events, and Prometheus rule/config failures.

These are Prometheus alert states only. Notification delivery requires Alertmanager or another alerting integration and is deliberately not exposed or invented here.
