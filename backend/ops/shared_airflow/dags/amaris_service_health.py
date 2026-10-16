"""Observe the website sharing this container; never mutate student/payment data."""

import os
from datetime import UTC, datetime, timedelta
from urllib import request

from airflow.sdk import dag, task


@dag(
    dag_id="amaris_service_health",
    schedule="*/10 * * * *",
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    tags=["amaris", "shared-container", "read-only"],
)
def service_health():
    @task(retries=1, retry_delay=timedelta(minutes=1), execution_timeout=timedelta(seconds=15))
    def check_website():
        url = os.environ["AMARIS_WEBSITE_READINESS_URL"]
        req = request.Request(url, headers={"X-Forwarded-Proto": "https"})
        with request.urlopen(req, timeout=10) as response:
            if response.status != 200:
                raise RuntimeError("Website readiness failed")
        return "ready"

    check_website()


service_health()
