"""Fail-closed, read-only Airflow health acceptance from a trusted private host.

Run from a Render shell with the private Airflow API network route. This tool
never prints the API token, raw HTTP error bodies or internal exception strings.
"""

import json
import os
import re
import ssl
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import parse, request

MAX_BODY_BYTES = 256 * 1024
DAG_RE = re.compile(r"^[A-Za-z0-9_.-]{1,180}$")


class ReadinessError(Exception):
    """Live Airflow acceptance has not been established."""


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _required(env, key):
    value = env.get(key, "").strip()
    if not value or value.startswith("REPLACE_"):
        raise ReadinessError("Missing required Airflow readiness configuration.")
    return value


def _parse_timestamp(value):
    if not isinstance(value, str):
        raise ReadinessError("The latest Airflow DAG run has no completion timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ReadinessError("Invalid DAG run completion timestamp.") from None
    if parsed.tzinfo is None:
        raise ReadinessError("DAG run completion timestamp must include a timezone.")
    return parsed.astimezone(timezone.utc)


def check(env, *, now=None):
    """Check authenticated private API, heartbeats and a recent successful DAG."""
    base = _required(env, "AIRFLOW_API_BASE_URL").rstrip("/")
    token = _required(env, "AIRFLOW_API_TOKEN")
    ca_file = Path(_required(env, "AIRFLOW_API_CA_CERT_FILE"))
    dag_id = _required(env, "AIRFLOW_MONITORED_DAG")
    parsed = parse.urlsplit(base)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ReadinessError("Airflow endpoint must be a private HTTPS origin.")
    if not DAG_RE.fullmatch(dag_id):
        raise ReadinessError("Invalid monitored DAG identifier.")
    if not ca_file.is_file():
        raise ReadinessError("The private Airflow CA certificate is unavailable.")
    age_minutes = _required(env, "AIRFLOW_MAX_RUN_AGE_MINUTES")
    try:
        maximum_age = int(age_minutes)
    except ValueError:
        raise ReadinessError("Invalid maximum DAG run age.") from None
    if maximum_age < 10 or maximum_age > 1440:
        raise ReadinessError("DAG run freshness threshold must be between 10 and 1440 minutes.")

    try:
        tls = ssl.create_default_context(cafile=str(ca_file))
        opener = request.build_opener(request.HTTPSHandler(context=tls), NoRedirect())

        def get(path, query=None):
            suffix = ("?" + parse.urlencode(query)) if query else ""
            req = request.Request(
                base + path + suffix,
                headers={"Accept": "application/json", "Authorization": "Bearer " + token},
                method="GET",
            )
            with opener.open(req, timeout=6) as response:
                if response.status != 200:
                    raise ReadinessError("Airflow API did not return HTTP 200.")
                body = response.read(MAX_BODY_BYTES + 1)
                if len(body) > MAX_BODY_BYTES:
                    raise ReadinessError("Airflow API response exceeds the size limit.")
                payload = json.loads(body)
                if not isinstance(payload, dict):
                    raise ReadinessError("Airflow API returned an invalid response.")
                return payload

        health = get("/api/v2/monitor/health")
        for component in ("metadatabase", "scheduler", "dag_processor"):
            component_health = health.get(component)
            if not isinstance(component_health, dict) or component_health.get("status") != "healthy":
                raise ReadinessError("Airflow metadata, scheduler or DAG processor is unhealthy.")

        dag = get("/api/v2/dags/" + parse.quote(dag_id, safe=""))
        if dag.get("dag_id") != dag_id or dag.get("is_paused") is not False:
            raise ReadinessError("The approved health DAG is unavailable or paused.")

        runs = get(
            "/api/v2/dags/" + parse.quote(dag_id, safe="") + "/dagRuns",
            {"limit": 1, "order_by": "-start_date"},
        ).get("dag_runs")
        if (
            not isinstance(runs, list)
            or len(runs) != 1
            or not isinstance(runs[0], dict)
            or runs[0].get("state") != "success"
        ):
            raise ReadinessError("There is no successful latest health DAG run.")
        finished = _parse_timestamp(runs[0].get("end_date"))
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or not -timedelta(minutes=5) <= current - finished <= timedelta(minutes=maximum_age):
            raise ReadinessError("The latest health DAG run is stale or timestamped in the future.")
    except ReadinessError:
        raise
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise ReadinessError("Authenticated private Airflow readiness could not be verified.") from None
    return {"status": "PASS", "dag_id": dag_id, "latest_run": "successful_and_fresh"}


def main():
    try:
        outcome = check(os.environ)
    except ReadinessError:
        print("FAIL: Airflow production-readiness acceptance is incomplete.", file=sys.stderr)
        return 1
    print("PASS: verified TLS, authenticated API, metadata, scheduler, DAG processor and recent health DAG.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
