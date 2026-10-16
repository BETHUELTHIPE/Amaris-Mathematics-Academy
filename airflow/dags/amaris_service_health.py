"""Read-only Amaris health workflow.

Checks actual public availability; no payment writes, student data or secrets.
Additional service-specific workflows must be integrated explicitly.
"""
import os
from datetime import datetime, timedelta, timezone
from urllib import error, request

from airflow.sdk import dag, task


@dag(
    dag_id="amaris_service_health",
    description="Periodic public checks for the Amaris backend and student website",
    start_date=datetime(2026, 10, 1, tzinfo=timezone.utc),
    schedule="*/10 * * * *",
    catchup=False,
    max_active_runs=1,
    tags=["amaris", "monitoring", "read-only"],
)
def amaris_service_health():
    @task(retries=2, retry_delay=timedelta(minutes=1), execution_timeout=timedelta(seconds=20))
    def check_backend():
        base = os.environ.get("AMARIS_BACKEND_PUBLIC_URL", "https://amaris-production-web.onrender.com").rstrip("/")
        with request.urlopen(f"{base}/health/ready/", timeout=10) as response:
            if response.status != 200:
                raise RuntimeError("The Amaris backend readiness check failed.")
        return "ready"

    @task(retries=2, retry_delay=timedelta(minutes=1), execution_timeout=timedelta(seconds=20))
    def check_student_site():
        url = os.environ.get(
            "AMARIS_STUDENT_PUBLIC_URL",
            "https://amaris-mathematics-academy-live-students.onrender.com",
        )
        with request.urlopen(url, timeout=10) as response:
            if response.status != 200:
                raise RuntimeError("The Amaris student website check failed.")
        return "reachable"

    check_backend()
    check_student_site()


amaris_service_health()
