from __future__ import annotations

import itertools
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

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
OIDC_REFRESH_SECONDS = env_int("LOADTEST_OIDC_REFRESH_SECONDS", 180)
OIDC_AUDIENCE = os.getenv("LOADTEST_OIDC_AUDIENCE", "amaris-staging").strip()
ACCEPTANCE_SEED_PATH = os.getenv(
    "LOADTEST_ACCEPTANCE_SEED_PATH",
    "/api/v1/student/acceptance/seed/",
).strip()
ACCEPTANCE_CHECKOUT_PATH = os.getenv(
    "LOADTEST_ACCEPTANCE_CHECKOUT_PATH",
    "/api/v1/student/checkout/",
).strip()

_STARTED_AT = 0.0
_MAX_USERS_OBSERVED = 0
_TARGET_SECONDS_OBSERVED = 0.0
_LOCAL_REQUESTS = 0
_LOCAL_5XX = 0
_WORKER_COUNTERS: dict[str, tuple[int, int, int, tuple[str, ...]]] = {}
_SEEN_REQUEST_NAMES: set[str] = set()
_RUNNER: Any = None
_STOP_SAMPLING = False
_AUTH_REFRESHED_AT = time.monotonic()
_AUTH_REFRESH_LOCK = threading.Lock()
_ACCEPTANCE_USER_COUNTER = itertools.count(1)


def _auth_available() -> bool:
    return bool(AUTH_BEARER or COOKIE_HEADER or (SESSION_COOKIE_NAME and SESSION_COOKIE_VALUE))


def _oidc_request_url() -> str:
    request_url = os.getenv("ACTIONS_ID_TOKEN_REQUEST_URL", "").strip()
    if not request_url:
        return ""
    parsed = urlsplit(request_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["audience"] = OIDC_AUDIENCE
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(query),
            parsed.fragment,
        )
    )


def _current_auth_bearer() -> str:
    global AUTH_BEARER
    global _AUTH_REFRESHED_AT

    if not ACCEPTANCE_HEADER:
        return AUTH_BEARER

    request_url = _oidc_request_url()
    request_token = os.getenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "").strip()
    if not request_url or not request_token:
        return AUTH_BEARER

    if AUTH_BEARER and time.monotonic() - _AUTH_REFRESHED_AT < OIDC_REFRESH_SECONDS:
        return AUTH_BEARER

    with _AUTH_REFRESH_LOCK:
        if AUTH_BEARER and time.monotonic() - _AUTH_REFRESHED_AT < OIDC_REFRESH_SECONDS:
            return AUTH_BEARER
        request = Request(
            request_url,
            headers={
                "Authorization": f"bearer {request_token}",
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise RuntimeError("GitHub OIDC refresh failed during capacity testing.") from exc
        refreshed = str(payload.get("value") or "").strip()
        if not refreshed:
            raise RuntimeError("GitHub OIDC refresh returned no token.")
        AUTH_BEARER = refreshed
        _AUTH_REFRESHED_AT = time.monotonic()
        return AUTH_BEARER


def _request_headers(
    *,
    protected: bool,
    acceptance_user: str = "",
) -> dict[str, str]:
    if not protected:
        return {}
    headers: dict[str, str] = {}
    bearer = _current_auth_bearer()
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
        if ACCEPTANCE_HEADER:
            headers["X-Amaris-Acceptance"] = "github-actions"
            if acceptance_user:
                headers["X-Amaris-Acceptance-User"] = acceptance_user
    elif COOKIE_HEADER:
        headers["Cookie"] = COOKIE_HEADER
    return headers


def _checked_get(
    user: Any,
    path: str,
    name: str,
    *,
    protected: bool = False,
    acceptance_user: str = "",
) -> None:
    if not path:
        return
    with user.client.get(
        path,
        name=name,
        headers=_request_headers(
            protected=protected,
            acceptance_user=acceptance_user,
        ),
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

    acceptance_user = ""
    payment_status_path = ENDPOINTS.payment_status

    def on_start(self) -> None:
        if SESSION_COOKIE_NAME and SESSION_COOKIE_VALUE and not (AUTH_BEARER or COOKIE_HEADER):
            self.client.cookies.set(
                SESSION_COOKIE_NAME,
                SESSION_COOKIE_VALUE,
            )
        if ACCEPTANCE_HEADER:
            self.acceptance_user = f"capacity-{os.getpid()}-{next(_ACCEPTANCE_USER_COUNTER)}"
            self._prepare_acceptance_identity()

    def _protected_headers(self) -> dict[str, str]:
        return _request_headers(
            protected=True,
            acceptance_user=self.acceptance_user,
        )

    def _prepare_acceptance_identity(self) -> None:
        headers = self._protected_headers()
        with self.client.post(
            ACCEPTANCE_SEED_PATH,
            name="00a Acceptance seed",
            headers={**headers, "Content-Type": "application/json"},
            data="{}",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"acceptance seed returned {response.status_code}")
                return

        idempotency_key = f"capacity-{self.acceptance_user}"
        checkout_body = json.dumps(
            {
                "course_slug": "acceptance-capacity-mathematics",
                "idempotency_key": idempotency_key,
            }
        )
        with self.client.post(
            ACCEPTANCE_CHECKOUT_PATH,
            name="00b Acceptance checkout",
            headers={**self._protected_headers(), "Content-Type": "application/json"},
            data=checkout_body,
            catch_response=True,
        ) as response:
            if response.status_code != 201:
                response.failure(f"acceptance checkout returned {response.status_code}")
                return
            try:
                reference = str(response.json()["payment_reference"])
            except (KeyError, TypeError, ValueError):
                response.failure("acceptance checkout omitted payment_reference")
                return

        self.payment_status_path = f"/api/v1/student/payments/{reference}/"

    @task(5)
    def dashboard(self) -> None:
        _checked_get(
            self,
            ENDPOINTS.dashboard,
            "07 Student dashboard",
            protected=True,
            acceptance_user=self.acceptance_user,
        )

    @task(6)
    def lesson_access(self) -> None:
        _checked_get(
            self,
            ENDPOINTS.lesson,
            "08 Lesson access",
            protected=True,
            acceptance_user=self.acceptance_user,
        )

    @task(3)
    def payment_status_polling(self) -> None:
        _checked_get(
            self,
            self.payment_status_path,
            "11 Payment-status polling",
            protected=True,
            acceptance_user=self.acceptance_user,
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
            if isinstance(runner, MasterRunner) and _WORKER_COUNTERS:
                user_count = sum(item[2] for item in _WORKER_COUNTERS.values())
            else:
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
    del request_type, response_time, response_length, exception
    global _LOCAL_REQUESTS, _LOCAL_5XX
    _LOCAL_REQUESTS += 1
    _SEEN_REQUEST_NAMES.add(name)
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
    data["capacity_user_count"] = int(getattr(_RUNNER, "user_count", 0))
    data["capacity_request_names"] = sorted(_SEEN_REQUEST_NAMES)


@events.worker_report.add_listener
def receive_capacity_counters(
    client_id: str,
    data: dict[str, Any],
    **_kwargs: Any,
) -> None:
    request_names = tuple(str(name) for name in data.get("capacity_request_names", []) if str(name))
    _WORKER_COUNTERS[client_id] = (
        int(data.get("capacity_request_count", 0)),
        int(data.get("capacity_5xx_count", 0)),
        int(data.get("capacity_user_count", 0)),
        request_names,
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
    global _RUNNER

    _RUNNER = environment.runner
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


def _effective_request_names(environment: Environment) -> set[str]:
    if isinstance(environment.runner, MasterRunner) and _WORKER_COUNTERS:
        names: set[str] = set()
        for item in _WORKER_COUNTERS.values():
            names.update(item[3])
        return names
    return set(_SEEN_REQUEST_NAMES)


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
    request_names = _effective_request_names(environment)
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
        "request_names": sorted(request_names),
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
    if REQUIRE_AUTH:
        required_authenticated_requests = {
            "07 Student dashboard",
            "08 Lesson access",
            "11 Payment-status polling",
        }
        missing_authenticated = sorted(required_authenticated_requests - request_names)
        if missing_authenticated:
            failures.append("authenticated traffic mix missing required samples: " + ", ".join(missing_authenticated))
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
