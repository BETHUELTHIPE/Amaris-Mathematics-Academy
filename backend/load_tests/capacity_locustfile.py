from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import gevent
from locust import LoadTestShape, between, events, task
from locust.contrib.fasthttp import FastHttpUser
from locust.env import Environment
from locust.runners import MasterRunner, WorkerRunner

from load_tests.capacity import CapacityThresholds, env_int, validate_capacity_level
from load_tests.config import Endpoints, env_bool, env_csv, validate_target

LOGGER = logging.getLogger(__name__)

TARGET_USERS = validate_capacity_level(env_int("CAPACITY_USERS", 100))
RAMP_SECONDS = env_int("CAPACITY_RAMP_SECONDS", 120)
HOLD_SECONDS = env_int("CAPACITY_HOLD_SECONDS", 300)
REQUIRE_AUTH = env_bool("CAPACITY_REQUIRE_AUTH", True)
RESULT_PATH = Path(
    os.getenv(
        "CAPACITY_LOCUST_RESULT",
        "load_tests/results/capacity-locust.json",
    )
)

ENDPOINTS = Endpoints.from_environment()
AUTH_BEARER = os.getenv("LOADTEST_AUTH_BEARER", "").strip()
COOKIE_HEADER = os.getenv("LOADTEST_COOKIE_HEADER", "").strip()
SESSION_COOKIE_NAME = os.getenv("LOADTEST_SESSION_COOKIE_NAME", "").strip()
SESSION_COOKIE_VALUE = os.getenv("LOADTEST_SESSION_COOKIE_VALUE", "").strip()
ACCEPTANCE_HEADER = env_bool("LOADTEST_ACCEPTANCE_HEADER", False)

_STARTED_AT = 0.0
_MAX_USERS_OBSERVED = 0
_TARGET_SECONDS_OBSERVED = 0.0
_LOCAL_REQUESTS = 0
_LOCAL_5XX = 0
_WORKER_COUNTERS: dict[str, tuple[int, int]] = {}
_STOP_SAMPLING = False


def _auth_available() -> bool:
    return bool(AUTH_BEARER or COOKIE_HEADER or (SESSION_COOKIE_NAME and SESSION_COOKIE_VALUE))


def _checked_get(
    user: Any,
    path: str,
    name: str,
    *,
    protected: bool = False,
) -> None:
    if not path:
        return
    with user.client.get(
        path,
        name=name,
        catch_response=True,
        allow_redirects=not protected,
    ) as response:
        expected = {200} if protected else {200, 301, 302, 303, 307, 308}
        if response.status_code not in expected:
            response.failure(f"unexpected status {response.status_code}")


class CapacityPublicUser(FastHttpUser):
    weight = 6
    wait_time = between(1.0, 2.5)

    @task(5)
    def homepage(self) -> None:
        _checked_get(self, ENDPOINTS.homepage, "01 Homepage")

    @task(4)
    def course_catalogue(self) -> None:
        _checked_get(self, ENDPOINTS.catalogue, "02 Course catalogue")

    @task(3)
    def course_search(self) -> None:
        _checked_get(self, ENDPOINTS.search, "03 Course search")

    @task(3)
    def course_details(self) -> None:
        _checked_get(self, ENDPOINTS.course_detail, "04 Course details")

    @task(1)
    def login_page(self) -> None:
        _checked_get(self, ENDPOINTS.login_page, "06a Login page")


class CapacityStudentUser(FastHttpUser):
    weight = 4 if REQUIRE_AUTH else 0
    wait_time = between(1.0, 2.0)

    def on_start(self) -> None:
        if AUTH_BEARER:
            self.client.headers.update({"Authorization": f"Bearer {AUTH_BEARER}"})
            if ACCEPTANCE_HEADER:
                self.client.headers.update({"X-Amaris-Acceptance": "github-actions"})
        elif COOKIE_HEADER:
            self.client.headers.update({"Cookie": COOKIE_HEADER})
        elif SESSION_COOKIE_NAME and SESSION_COOKIE_VALUE:
            self.client.cookies.set(
                SESSION_COOKIE_NAME,
                SESSION_COOKIE_VALUE,
            )

    @task(5)
    def dashboard(self) -> None:
        _checked_get(
            self,
            ENDPOINTS.dashboard,
            "07 Student dashboard",
            protected=True,
        )

    @task(6)
    def lesson_access(self) -> None:
        _checked_get(
            self,
            ENDPOINTS.lesson,
            "08 Lesson access",
            protected=True,
        )

    @task(3)
    def payment_status_polling(self) -> None:
        _checked_get(
            self,
            ENDPOINTS.payment_status,
            "11 Payment-status polling",
            protected=True,
        )


class CapacityShape(LoadTestShape):
    def tick(self):
        run_time = self.get_run_time()
        spawn_rate = max(1.0, TARGET_USERS / RAMP_SECONDS)
        if run_time < RAMP_SECONDS:
            ramp_fraction = max(run_time / RAMP_SECONDS, 1 / TARGET_USERS)
            return max(1, int(TARGET_USERS * ramp_fraction)), spawn_rate
        if run_time < RAMP_SECONDS + HOLD_SECONDS:
            return TARGET_USERS, spawn_rate
        return None


def _is_worker(environment: Environment) -> bool:
    return isinstance(environment.runner, WorkerRunner)


def _sample_users(environment: Environment) -> None:
    global _MAX_USERS_OBSERVED, _TARGET_SECONDS_OBSERVED

    previous_sample_at = time.monotonic()
    while not _STOP_SAMPLING:
        now = time.monotonic()
        elapsed = max(0.0, min(now - previous_sample_at, 2.0))
        previous_sample_at = now

        runner = environment.runner
        if runner is not None and not isinstance(runner, WorkerRunner):
            user_count = int(getattr(runner, "user_count", 0))
            _MAX_USERS_OBSERVED = max(
                _MAX_USERS_OBSERVED,
                user_count,
            )
            if user_count >= TARGET_USERS:
                _TARGET_SECONDS_OBSERVED += elapsed
        gevent.sleep(1)


@events.request.add_listener
def count_requests(
    request_type: str,
    name: str,
    response_time: float,
    response_length: int,
    response: Any = None,
    exception: Exception | None = None,
    **_kwargs: Any,
) -> None:
    del request_type, name, response_time, response_length, exception
    global _LOCAL_REQUESTS, _LOCAL_5XX
    _LOCAL_REQUESTS += 1
    status_code = getattr(response, "status_code", 0)
    if isinstance(status_code, int) and status_code >= 500:
        _LOCAL_5XX += 1


@events.report_to_master.add_listener
def report_capacity_counters(
    client_id: str,
    data: dict[str, Any],
    **_kwargs: Any,
) -> None:
    del client_id
    data["capacity_request_count"] = _LOCAL_REQUESTS
    data["capacity_5xx_count"] = _LOCAL_5XX


@events.worker_report.add_listener
def receive_capacity_counters(
    client_id: str,
    data: dict[str, Any],
    **_kwargs: Any,
) -> None:
    _WORKER_COUNTERS[client_id] = (
        int(data.get("capacity_request_count", 0)),
        int(data.get("capacity_5xx_count", 0)),
    )


@events.test_start.add_listener
def validate_capacity_run(
    environment: Environment,
    **_kwargs: Any,
) -> None:
    global _STARTED_AT
    global _MAX_USERS_OBSERVED
    global _TARGET_SECONDS_OBSERVED
    global _STOP_SAMPLING

    target_url = environment.host or os.getenv("LOADTEST_TARGET_URL", "")
    validate_target(
        target_url,
        environment_name=os.getenv(
            "LOADTEST_ENVIRONMENT",
            "capacity",
        )
        .strip()
        .lower(),
        allowed_hosts=env_csv("LOADTEST_ALLOWED_HOSTS"),
        allow_production=env_bool("LOADTEST_ALLOW_PRODUCTION"),
        allow_live_payfast=False,
    )

    if REQUIRE_AUTH:
        if not _auth_available():
            raise RuntimeError(
                "Representative capacity testing requires a dedicated " "synthetic authentication credential."
            )
        missing = []
        if not ENDPOINTS.lesson:
            missing.append("LOADTEST_LESSON_PATH")
        if not ENDPOINTS.payment_status:
            missing.append("LOADTEST_PAYMENT_STATUS_PATH")
        if missing:
            joined = ", ".join(missing)
            raise RuntimeError(f"Representative capacity testing requires: {joined}")

    if not _is_worker(environment):
        _STARTED_AT = time.monotonic()
        _MAX_USERS_OBSERVED = 0
        _TARGET_SECONDS_OBSERVED = 0.0
        _STOP_SAMPLING = False
        gevent.spawn(_sample_users, environment)


def _effective_counters(environment: Environment) -> tuple[int, int]:
    if isinstance(environment.runner, MasterRunner):
        if _WORKER_COUNTERS:
            return (
                sum(item[0] for item in _WORKER_COUNTERS.values()),
                sum(item[1] for item in _WORKER_COUNTERS.values()),
            )
        return environment.stats.total.num_requests, 0
    return _LOCAL_REQUESTS, _LOCAL_5XX


@events.quitting.add_listener
def write_capacity_evidence(
    environment: Environment,
    **_kwargs: Any,
) -> None:
    global _STOP_SAMPLING
    if _is_worker(environment):
        return

    _STOP_SAMPLING = True
    threshold = CapacityThresholds.from_environment()
    total = environment.stats.total
    request_count, server_5xx_count = _effective_counters(environment)
    duration_seconds = max(time.monotonic() - _STARTED_AT, 0.001)
    failure_pct = total.fail_ratio * 100.0
    server_5xx_pct = server_5xx_count / request_count * 100.0 if request_count else 0.0
    minimum_hold_seconds = max(1.0, HOLD_SECONDS - 15.0)

    evidence = {
        "target_users": TARGET_USERS,
        "max_users_observed": _MAX_USERS_OBSERVED,
        "target_reached": _MAX_USERS_OBSERVED >= TARGET_USERS,
        "target_hold_seconds_required": HOLD_SECONDS,
        "target_hold_seconds_observed": round(
            _TARGET_SECONDS_OBSERVED,
            3,
        ),
        "target_hold_sustained": (_TARGET_SECONDS_OBSERVED >= minimum_hold_seconds),
        "duration_seconds": round(duration_seconds, 3),
        "requests": int(total.num_requests),
        "failures": int(total.num_failures),
        "failure_pct": round(failure_pct, 6),
        "server_5xx": int(server_5xx_count),
        "server_5xx_pct": round(server_5xx_pct, 6),
        "rps": round(total.num_requests / duration_seconds, 3),
        "p50_ms": (total.get_response_time_percentile(0.50) if total.num_requests else 0),
        "p90_ms": (total.get_response_time_percentile(0.90) if total.num_requests else 0),
        "p95_ms": (total.get_response_time_percentile(0.95) if total.num_requests else 0),
        "p99_ms": (total.get_response_time_percentile(0.99) if total.num_requests else 0),
        "thresholds": {
            "max_failure_pct": threshold.failure_pct,
            "max_5xx_pct": threshold.server_5xx_pct,
            "max_p95_ms": threshold.p95_ms,
            "max_p99_ms": threshold.p99_ms,
            "minimum_target_hold_seconds": minimum_hold_seconds,
        },
    }

    failures: list[str] = []
    if total.num_requests == 0:
        failures.append("no requests were recorded")
    if _MAX_USERS_OBSERVED < TARGET_USERS:
        failures.append(f"only {_MAX_USERS_OBSERVED:,} of " f"{TARGET_USERS:,} target users were observed")
    if _TARGET_SECONDS_OBSERVED < minimum_hold_seconds:
        failures.append(
            f"target concurrency was sustained for only "
            f"{_TARGET_SECONDS_OBSERVED:.1f}s; at least "
            f"{minimum_hold_seconds:.1f}s is required"
        )
    if failure_pct > threshold.failure_pct:
        failures.append(f"failure rate {failure_pct:.3f}% exceeded " f"{threshold.failure_pct:.3f}%")
    if server_5xx_pct > threshold.server_5xx_pct:
        failures.append(f"5xx rate {server_5xx_pct:.3f}% exceeded " f"{threshold.server_5xx_pct:.3f}%")
    if evidence["p95_ms"] > threshold.p95_ms:
        failures.append(f"p95 {evidence['p95_ms']}ms exceeded " f"{threshold.p95_ms}ms")
    if evidence["p99_ms"] > threshold.p99_ms:
        failures.append(f"p99 {evidence['p99_ms']}ms exceeded " f"{threshold.p99_ms}ms")

    evidence["locust_gate_passed"] = not failures
    evidence["locust_gate_failures"] = failures

    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(
        json.dumps(evidence, indent=2) + "\n",
        encoding="utf-8",
    )

    if failures:
        for failure in failures:
            LOGGER.error("CAPACITY LOCUST GATE: %s", failure)
        environment.process_exit_code = 1
    else:
        LOGGER.info(
            "Capacity Locust gate passed at %s concurrent users.",
            f"{TARGET_USERS:,}",
        )
        environment.process_exit_code = 0
