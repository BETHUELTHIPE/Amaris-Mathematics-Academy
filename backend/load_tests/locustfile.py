from __future__ import annotations

import logging
import os
import uuid

from locust import HttpUser, LoadTestShape, between, events, task
from locust.env import Environment

from load_tests.config import (
    AUTHENTICATED_REQUESTS,
    PUBLIC_REQUESTS,
    THRESHOLDS,
    TRAFFIC_STAGES,
    WRITE_REQUESTS,
    Endpoints,
    env_bool,
    env_csv,
    missing_full_journey_configuration,
    validate_target,
)

LOGGER = logging.getLogger(__name__)
PROFILE = os.getenv("LOADTEST_PROFILE", "normal").strip().lower()
if PROFILE not in TRAFFIC_STAGES:
    raise ValueError(f"Unknown LOADTEST_PROFILE {PROFILE!r}.")

ENDPOINTS = Endpoints.from_environment()
ALLOW_WRITES = env_bool("LOADTEST_ALLOW_WRITES")
REQUIRE_FULL_JOURNEY = env_bool("LOADTEST_REQUIRE_FULL_JOURNEY")
AUTH_BEARER = os.getenv("LOADTEST_AUTH_BEARER", "").strip()
COOKIE_HEADER = os.getenv("LOADTEST_COOKIE_HEADER", "").strip()
SESSION_COOKIE_NAME = os.getenv("LOADTEST_SESSION_COOKIE_NAME", "").strip()
SESSION_COOKIE_VALUE = os.getenv("LOADTEST_SESSION_COOKIE_VALUE", "").strip()
LOGIN_EMAIL = os.getenv("LOADTEST_LOGIN_EMAIL", "").strip()
LOGIN_PASSWORD = os.getenv("LOADTEST_LOGIN_PASSWORD", "").strip()
REGISTRATION_PASSWORD = os.getenv("LOADTEST_REGISTRATION_PASSWORD", "").strip()
REGISTRATION_EMAIL_DOMAIN = os.getenv("LOADTEST_REGISTRATION_EMAIL_DOMAIN", "").strip().lower()
COURSE_ID = os.getenv("LOADTEST_COURSE_ID", "").strip() or "load-test-course"
LESSON_ID = os.getenv("LOADTEST_LESSON_ID", "").strip() or "load-test-lesson"


def checked_get(user: HttpUser, path: str, name: str, *, protected: bool = False) -> None:
    if not path:
        return
    with user.client.get(path, name=name, catch_response=True, allow_redirects=not protected) as response:
        expected = {200} if protected else {200, 301, 302, 303, 307, 308}
        if response.status_code not in expected:
            response.failure(f"unexpected status {response.status_code}")


def checked_post(user: HttpUser, path: str, name: str, payload: dict[str, object]) -> None:
    if not path or not ALLOW_WRITES:
        return
    with user.client.post(path, name=name, json=payload, catch_response=True, allow_redirects=False) as response:
        if response.status_code not in {200, 201, 202, 204, 302, 303}:
            response.failure(f"unexpected status {response.status_code}")


class PublicJourneyUser(HttpUser):
    weight = 6
    wait_time = between(1.0, 3.0)

    @task(5)
    def homepage(self) -> None:
        checked_get(self, ENDPOINTS.homepage, "01 Homepage")

    @task(4)
    def course_catalogue(self) -> None:
        checked_get(self, ENDPOINTS.catalogue, "02 Course catalogue")

    @task(3)
    def course_search(self) -> None:
        checked_get(self, ENDPOINTS.search, "03 Course search")

    @task(3)
    def course_details(self) -> None:
        checked_get(self, ENDPOINTS.course_detail, "04 Course details")

    @task(1)
    def registration(self) -> None:
        checked_get(self, ENDPOINTS.registration_page, "05a Registration page")
        if ENDPOINTS.registration_submit and ALLOW_WRITES and REGISTRATION_PASSWORD and REGISTRATION_EMAIL_DOMAIN:
            unique_email = f"loadtest+{uuid.uuid4().hex}@{REGISTRATION_EMAIL_DOMAIN}"
            checked_post(
                self,
                ENDPOINTS.registration_submit,
                "05b Registration submit",
                {
                    "first_name": "Load",
                    "last_name": "Test",
                    "email": unique_email,
                    "password": REGISTRATION_PASSWORD,
                    "terms_accepted": True,
                    "privacy_accepted": True,
                },
            )

    @task(2)
    def login(self) -> None:
        checked_get(self, ENDPOINTS.login_page, "06a Login page")
        if ENDPOINTS.login_submit and ALLOW_WRITES and LOGIN_EMAIL and LOGIN_PASSWORD:
            checked_post(
                self,
                ENDPOINTS.login_submit,
                "06b Login submit",
                {"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
            )


class AuthenticatedStudentUser(HttpUser):
    weight = 4
    wait_time = between(1.0, 2.5)

    def on_start(self) -> None:
        self.authenticated = False
        if AUTH_BEARER:
            self.client.headers.update({"Authorization": f"Bearer {AUTH_BEARER}"})
            self.authenticated = True
        elif COOKIE_HEADER:
            self.client.headers.update({"Cookie": COOKIE_HEADER})
            self.authenticated = True
        elif SESSION_COOKIE_NAME and SESSION_COOKIE_VALUE:
            self.client.cookies.set(SESSION_COOKIE_NAME, SESSION_COOKIE_VALUE)
            self.authenticated = True

    @task(4)
    def dashboard(self) -> None:
        checked_get(self, ENDPOINTS.dashboard, "07 Student dashboard", protected=self.authenticated)

    @task(5)
    def lesson_access(self) -> None:
        if self.authenticated:
            checked_get(self, ENDPOINTS.lesson, "08 Lesson access", protected=True)

    @task(2)
    def progress_update(self) -> None:
        if self.authenticated:
            checked_post(
                self,
                ENDPOINTS.progress,
                "09 Progress update",
                {"lesson_id": LESSON_ID, "completed": True},
            )

    @task(1)
    def checkout_creation(self) -> None:
        if self.authenticated:
            # Redirects are deliberately disabled: the application order endpoint is tested,
            # but Locust never follows the user into PayFast.
            checked_post(
                self,
                ENDPOINTS.checkout,
                "10 Checkout creation",
                {"course_id": COURSE_ID},
            )

    @task(3)
    def payment_status_polling(self) -> None:
        if self.authenticated:
            checked_get(self, ENDPOINTS.payment_status, "11 Payment-status polling", protected=True)


class AmarisTrafficShape(LoadTestShape):
    def tick(self):
        run_time = self.get_run_time()
        for until_second, users, spawn_rate in TRAFFIC_STAGES[PROFILE]:
            if run_time < until_second:
                return users, spawn_rate
        return None


@events.test_start.add_listener
def validate_run(environment: Environment, **_kwargs) -> None:
    target_url = environment.host or os.getenv("LOADTEST_TARGET_URL", "")
    validate_target(
        target_url,
        environment_name=os.getenv("LOADTEST_ENVIRONMENT", "local").strip().lower(),
        allowed_hosts=env_csv("LOADTEST_ALLOWED_HOSTS", "localhost,127.0.0.1"),
        allow_production=env_bool("LOADTEST_ALLOW_PRODUCTION"),
        allow_live_payfast=env_bool("LOADTEST_ALLOW_LIVE_PAYFAST"),
    )
    if REQUIRE_FULL_JOURNEY:
        missing = missing_full_journey_configuration(ENDPOINTS)
        if missing:
            raise RuntimeError(f"Full journey requires: {', '.join(missing)}")
        if not ALLOW_WRITES:
            raise RuntimeError("Full journey requires LOADTEST_ALLOW_WRITES=true.")
        if not (AUTH_BEARER or COOKIE_HEADER or (SESSION_COOKIE_NAME and SESSION_COOKIE_VALUE)):
            raise RuntimeError("Full journey requires a staging bearer token or session cookie.")
        if not LOGIN_EMAIL or not LOGIN_PASSWORD:
            raise RuntimeError("Full journey requires the dedicated staging login credentials.")
        if not REGISTRATION_PASSWORD or not REGISTRATION_EMAIL_DOMAIN:
            raise RuntimeError("Full journey requires the staging registration password and email sink domain.")


def request_percentile(environment: Environment, request_name: str, percentile: float) -> int:
    values = [
        entry.get_response_time_percentile(percentile)
        for (name, _method), entry in environment.stats.entries.items()
        if name == request_name and entry.num_requests
    ]
    return max(values, default=0)


@events.quitting.add_listener
def enforce_service_levels(environment: Environment, **_kwargs) -> None:
    threshold = THRESHOLDS[PROFILE]
    failures: list[str] = []
    total = environment.stats.total
    p95 = total.get_response_time_percentile(0.95) if total.num_requests else 0
    p99 = total.get_response_time_percentile(0.99) if total.num_requests else 0

    if total.num_requests == 0:
        failures.append("no requests were recorded")
    if total.fail_ratio > threshold.failure_ratio:
        failures.append(f"failure ratio {total.fail_ratio:.2%} exceeded {threshold.failure_ratio:.2%}")
    if p95 > threshold.overall_p95_ms:
        failures.append(f"overall p95 {p95}ms exceeded {threshold.overall_p95_ms}ms")
    if p99 > threshold.overall_p99_ms:
        failures.append(f"overall p99 {p99}ms exceeded {threshold.overall_p99_ms}ms")

    p95_limits = {
        **{name: threshold.public_p95_ms for name in PUBLIC_REQUESTS},
        **{name: threshold.authenticated_p95_ms for name in AUTHENTICATED_REQUESTS},
        **{name: threshold.write_p95_ms for name in WRITE_REQUESTS},
    }
    for request_name, limit in p95_limits.items():
        observed = request_percentile(environment, request_name, 0.95)
        if observed and observed > limit:
            failures.append(f"{request_name} p95 {observed}ms exceeded {limit}ms")

    for request_name in PUBLIC_REQUESTS:
        observed = request_percentile(environment, request_name, 0.99)
        if observed and observed > threshold.public_p99_ms:
            failures.append(f"{request_name} p99 {observed}ms exceeded {threshold.public_p99_ms}ms")

    if REQUIRE_FULL_JOURNEY:
        recorded = {name for name, _method in environment.stats.entries}
        required = PUBLIC_REQUESTS | AUTHENTICATED_REQUESTS | WRITE_REQUESTS
        for missing_name in sorted(required - recorded):
            failures.append(f"required journey produced no samples for {missing_name}")

    if failures:
        for failure in failures:
            LOGGER.error("LOAD TEST GATE: %s", failure)
        environment.process_exit_code = 1
    else:
        LOGGER.info("Load-test service-level objectives passed for profile %s.", PROFILE)
        environment.process_exit_code = 0
