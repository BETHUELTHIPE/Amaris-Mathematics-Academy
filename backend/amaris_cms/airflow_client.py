"""Read-only Apache Airflow 3 API client for the Django superuser console.

Never accepts an arbitrary URL or DAG name from an unauthenticated user.
No Airflow credentials, raw exception messages or task logs enter HTML responses.
"""

import json
import re
import ssl
from datetime import timedelta
from urllib import error as url_error
from urllib import parse as url_parse
from urllib import request as url_request

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

MAX_BODY = 256 * 1024
MAX_WORKFLOWS = 12
DAG_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,180}$")


class AirflowUnavailable(Exception):
    """Airflow has not been configured or its read-only API cannot be reached."""


def monitored_dags():
    configured = getattr(settings, "AIRFLOW_MONITORED_DAGS", [])
    if not isinstance(configured, (list, tuple)):
        return ()
    return tuple(
        dict.fromkeys(
            dag_id
            for dag_id in configured[:MAX_WORKFLOWS]
            if isinstance(dag_id, str) and DAG_ID_RE.fullmatch(dag_id) and dag_id not in {".", ".."}
        )
    )


def is_configured():
    base = _safe_url(getattr(settings, "AIRFLOW_API_BASE_URL", ""), origin_only=True)
    token = getattr(settings, "AIRFLOW_API_TOKEN", "")
    return bool(
        getattr(settings, "AIRFLOW_MONITORING_ENABLED", False)
        and base
        and token
        and isinstance(token, str)
        and not any(ord(char) < 33 or ord(char) > 126 for char in token)
        and monitored_dags()
    )


def get_airflow_ui_url():
    """Return only a safely configured UI launch URL, never an API token.

    Airflow's own authentication still protects its browser interface.
    """
    return _safe_url(getattr(settings, "AIRFLOW_UI_URL", ""))


def _safe_url(raw, *, origin_only=False):
    if (
        not isinstance(raw, str)
        or not raw
        or "\\" in raw
        or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in raw)
    ):
        return ""
    try:
        parsed = url_parse.urlsplit(raw)
        # Invalid ports raise ValueError; reject malformed destinations.
        if parsed.port == 0:
            return ""
    except ValueError:
        return ""
    if not parsed.hostname or "@" in parsed.netloc or parsed.username or parsed.password:
        return ""
    if parsed.query or parsed.fragment:
        return ""
    if origin_only and parsed.path not in {"", "/"}:
        return ""
    local_debug = settings.DEBUG and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (local_debug and parsed.scheme == "http"):
        return ""
    return raw.rstrip("/")


def _read(path, query=None):
    if not is_configured():
        raise AirflowUnavailable("Airflow is not configured.")
    base = _safe_url(settings.AIRFLOW_API_BASE_URL, origin_only=True)
    if not path.startswith("/api/v2/"):
        raise ValueError("Unsupported Airflow API path.")
    target = base + path
    if query:
        target += "?" + url_parse.urlencode(query)

    req = url_request.Request(
        target,
        method="GET",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {settings.AIRFLOW_API_TOKEN}",
        },
    )
    try:
        # urllib uses validated TLS certificates by default; no redirect to
        # untrusted destinations is permitted for credential-bearing requests.
        context = ssl.create_default_context(cafile=getattr(settings, "AIRFLOW_API_CA_CERT_FILE", "") or None)
        opener = url_request.build_opener(_NoRedirect(), url_request.HTTPSHandler(context=context))
        with opener.open(req, timeout=4) as response:
            if response.status != 200:
                raise AirflowUnavailable("Airflow returned an unexpected status.")
            body = response.read(MAX_BODY + 1)
        if len(body) > MAX_BODY:
            raise AirflowUnavailable("Airflow API response is too large.")
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise AirflowUnavailable("Invalid Airflow API response.")
        return payload
    except (url_error.HTTPError, url_error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise AirflowUnavailable("Airflow API is currently unavailable.") from exc


class _NoRedirect(url_request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _assert_allowed(dag_id):
    if dag_id not in monitored_dags():
        raise ValueError("This workflow is not allowlisted.")


def get_airflow_health():
    """HTTP 200 alone does not prove that Airflow components are healthy."""
    payload = _read("/api/v2/monitor/health")
    components = []
    for name, title in (
        ("metadatabase", "Metadata database"),
        ("scheduler", "Scheduler"),
        ("dag_processor", "DAG processor"),
    ):
        item = payload.get(name)
        status = item.get("status") if isinstance(item, dict) else None
        components.append(
            {
                "title": title,
                "status": status if isinstance(status, str) and status in {"healthy", "unhealthy"} else "unknown",
            }
        )
    return {"healthy": all(item["status"] == "healthy" for item in components), "components": components}


def check_runtime(dag_id, *, max_run_age_minutes=30):
    """Read-only runtime acceptance: components, unpaused DAG and fresh success."""
    _assert_allowed(dag_id)
    if not 10 <= max_run_age_minutes <= 1440:
        raise ValueError("Run freshness must be between 10 and 1440 minutes.")
    if not get_airflow_health()["healthy"]:
        raise AirflowUnavailable("Required Airflow components are unhealthy or unknown.")
    metadata = _read(f"/api/v2/dags/{url_parse.quote(dag_id, safe='')}")
    if metadata.get("dag_id") != dag_id or metadata.get("is_paused") is not False:
        raise AirflowUnavailable("The health workflow is unavailable or paused.")
    summary = get_workflow(dag_id)
    try:
        finished = parse_datetime(summary["end_date"]) if isinstance(summary["end_date"], str) else None
    except ValueError:
        finished = None
    if (
        summary["state"] != "success"
        or summary["run_type"] != "scheduled"
        or finished is None
        or timezone.is_naive(finished)
    ):
        raise AirflowUnavailable("No successful timestamped health workflow run is available.")
    age = timezone.now() - finished
    if not -timedelta(minutes=5) <= age <= timedelta(minutes=max_run_age_minutes):
        raise AirflowUnavailable("The health workflow is stale or timestamped in the future.")
    return {"status": "PASS", "dag_id": dag_id, "latest_run": "successful_and_fresh"}


def get_workflow(dag_id):
    """Latest confirmed Airflow run for one allowlisted workflow."""
    _assert_allowed(dag_id)
    name = url_parse.quote(dag_id, safe="")
    payload = _read(f"/api/v2/dags/{name}/dagRuns", {"limit": 1, "order_by": "-start_date"})
    runs = payload.get("dag_runs", [])
    if not isinstance(runs, list):
        raise AirflowUnavailable("Invalid workflow response.")
    run = runs[0] if runs and isinstance(runs[0], dict) else {}
    return {
        "dag_id": dag_id,
        "run_id": str(run.get("dag_run_id", ""))[:200],
        "run_type": str(run.get("run_type", ""))[:32],
        "state": str(run.get("state", "never_run"))[:32],
        "start_date": run.get("start_date"),
        "end_date": run.get("end_date"),
    }


def get_workflow_tasks(dag_id):
    """Read-only snapshot of last run task states; never triggers jobs."""
    summary = get_workflow(dag_id)
    run_id = summary["run_id"]
    if not run_id:
        return summary, []
    dag = url_parse.quote(dag_id, safe="")
    run = url_parse.quote(run_id, safe="")
    payload = _read(
        f"/api/v2/dags/{dag}/dagRuns/{run}/taskInstances",
        {"limit": 100},
    )
    items = payload.get("task_instances", [])
    if not isinstance(items, list):
        raise AirflowUnavailable("Invalid task response.")
    tasks = [
        {
            "task_id": str(item.get("task_id", ""))[:180],
            "state": str(item.get("state") or "waiting")[:32],
            "try_number": item.get("try_number"),
            "start_date": item.get("start_date"),
            "end_date": item.get("end_date"),
        }
        for item in items[:100]
        if isinstance(item, dict)
    ]
    return summary, tasks
