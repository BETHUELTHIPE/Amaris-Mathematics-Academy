"""Read-only Apache Airflow 3 API client for the Django superuser console.

Never accepts an arbitrary URL or DAG name from an unauthenticated user.
No Airflow credentials, raw exception messages or task logs enter HTML responses.
"""
import json
import re
from urllib import error as url_error
from urllib import parse as url_parse
from urllib import request as url_request

from django.conf import settings

MAX_BODY = 256 * 1024
MAX_WORKFLOWS = 12
DAG_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,180}$")


class AirflowUnavailable(Exception):
    """Airflow has not been configured or its read-only API cannot be reached."""


def monitored_dags():
    configured = getattr(settings, "AIRFLOW_MONITORED_DAGS", [])
    return tuple(dag_id for dag_id in configured[:MAX_WORKFLOWS] if DAG_ID_RE.fullmatch(dag_id))


def is_configured():
    base = getattr(settings, "AIRFLOW_API_BASE_URL", "").rstrip("/")
    token = getattr(settings, "AIRFLOW_API_TOKEN", "")
    parsed = url_parse.urlsplit(base)
    # Only an operator-configured HTTPS address is permitted in production.
    return bool(
        getattr(settings, "AIRFLOW_MONITORING_ENABLED", False)
        and token
        and monitored_dags()
        and parsed.hostname
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
        and (parsed.scheme == "https" or (settings.DEBUG and parsed.scheme == "http"))
    )


def _read(path, query=None):
    if not is_configured():
        raise AirflowUnavailable("Airflow is not configured.")
    base = settings.AIRFLOW_API_BASE_URL.rstrip("/")
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
        opener = url_request.build_opener(_NoRedirect())
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
