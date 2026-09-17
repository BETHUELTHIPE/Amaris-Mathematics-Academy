from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_csv(name: str, default: str = "") -> tuple[str, ...]:
    return tuple(value.strip().lower() for value in os.getenv(name, default).split(",") if value.strip())


def relative_path(name: str, default: str = "") -> str:
    value = os.getenv(name, default).strip()
    if value and (not value.startswith("/") or value.startswith("//")):
        raise ValueError(f"{name} must be a relative application path beginning with one slash.")
    return value


@dataclass(frozen=True)
class Endpoints:
    homepage: str = "/"
    catalogue: str = "/courses"
    search: str = "/courses?search=algebra"
    course_detail: str = "/courses/university-calculus-foundations"
    registration_page: str = "/register"
    registration_submit: str = ""
    login_page: str = "/login"
    login_submit: str = ""
    dashboard: str = "/dashboard"
    lesson: str = ""
    progress: str = ""
    checkout: str = ""
    payment_status: str = ""

    @classmethod
    def from_environment(cls) -> Endpoints:
        return cls(
            homepage=relative_path("LOADTEST_HOMEPAGE_PATH", "/"),
            catalogue=relative_path("LOADTEST_CATALOGUE_PATH", "/courses"),
            search=relative_path("LOADTEST_SEARCH_PATH", "/courses?search=algebra"),
            course_detail=relative_path("LOADTEST_COURSE_DETAIL_PATH", "/courses/university-calculus-foundations"),
            registration_page=relative_path("LOADTEST_REGISTRATION_PAGE_PATH", "/register"),
            registration_submit=relative_path("LOADTEST_REGISTRATION_SUBMIT_PATH"),
            login_page=relative_path("LOADTEST_LOGIN_PAGE_PATH", "/login"),
            login_submit=relative_path("LOADTEST_LOGIN_SUBMIT_PATH"),
            dashboard=relative_path("LOADTEST_DASHBOARD_PATH", "/dashboard"),
            lesson=relative_path("LOADTEST_LESSON_PATH"),
            progress=relative_path("LOADTEST_PROGRESS_PATH"),
            checkout=relative_path("LOADTEST_CHECKOUT_PATH"),
            payment_status=relative_path("LOADTEST_PAYMENT_STATUS_PATH"),
        )


@dataclass(frozen=True)
class Thresholds:
    failure_ratio: float
    overall_p95_ms: int
    overall_p99_ms: int
    public_p95_ms: int
    public_p99_ms: int
    authenticated_p95_ms: int
    write_p95_ms: int


# Production gates mirror the signed performance architecture: public reads p95
# <=500 ms and p99 <=1 s, authenticated reads p95 <=750 ms, checkout/writes
# p95 <=1 s, normal errors strictly below 1%, and peak errors strictly below 2%.
THRESHOLDS: dict[str, Thresholds] = {
    "smoke": Thresholds(0.009, 750, 1500, 500, 1000, 750, 1000),
    "normal": Thresholds(0.009, 750, 1500, 500, 1000, 750, 1000),
    "elevated": Thresholds(0.019, 1000, 2000, 500, 1000, 750, 1000),
    "peak": Thresholds(0.019, 1000, 2000, 500, 1000, 750, 1000),
    "spike": Thresholds(0.019, 1250, 2500, 500, 1000, 750, 1000),
    "degraded": Thresholds(0.05, 3000, 6000, 2500, 4000, 3000, 4000),
}

# Capacity scenarios are intentionally representative, not token CI traffic.
# Manual normal/elevated/peak/spike runs must use the dedicated load generator.
TRAFFIC_STAGES: dict[str, tuple[tuple[int, int, int], ...]] = {
    "smoke": ((5, 5, 2), (35, 5, 2)),
    "normal": ((300, 2500, 50), (600, 5000, 100), (1200, 5000, 100), (1320, 0, 100)),
    "elevated": ((300, 5000, 100), (600, 7500, 150), (1200, 10000, 200), (1320, 0, 200)),
    "peak": ((300, 10000, 200), (600, 15000, 300), (1200, 25000, 500), (1320, 0, 500)),
    "spike": ((60, 2500, 100), (180, 25000, 1000), (480, 25000, 500), (600, 5000, 500), (720, 0, 500)),
    "degraded": ((15, 10, 5), (90, 10, 2), (105, 0, 5)),
}

PUBLIC_REQUESTS = {
    "01 Homepage",
    "02 Course catalogue",
    "03 Course search",
    "04 Course details",
    "05a Registration page",
    "06a Login page",
}
AUTHENTICATED_REQUESTS = {"07 Student dashboard", "08 Lesson access", "11 Payment-status polling"}
WRITE_REQUESTS = {"05b Registration submit", "06b Login submit", "09 Progress update", "10 Checkout creation"}

PAYFAST_HOSTS = {"www.payfast.co.za", "sandbox.payfast.co.za", "api.payfast.co.za"}
KNOWN_PRODUCTION_HOSTS = {"amaris-mathematics-academy.bethuelthipe.chatgpt.site"}


def validate_target(
    target_url: str,
    *,
    environment_name: str,
    allowed_hosts: tuple[str, ...],
    allow_production: bool,
    allow_live_payfast: bool,
) -> str:
    parsed = urlparse(target_url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise ValueError("LOADTEST_TARGET_URL/--host must be a complete HTTP or HTTPS URL.")
    if parsed.username or parsed.password:
        raise ValueError("Do not place credentials in the load-test target URL.")
    if hostname in PAYFAST_HOSTS and not allow_live_payfast:
        raise ValueError("Direct PayFast load testing is blocked without explicit written authorisation.")
    if hostname in KNOWN_PRODUCTION_HOSTS and not allow_production:
        raise ValueError("The live Amaris Site is blocked. Use the staging environment.")
    if environment_name == "production" and not allow_production:
        raise ValueError("Production load testing requires explicit authorisation.")
    if allowed_hosts and hostname not in allowed_hosts:
        raise ValueError(f"Target host {hostname!r} is not in LOADTEST_ALLOWED_HOSTS.")
    return hostname


def missing_full_journey_configuration(endpoints: Endpoints) -> list[str]:
    required = {
        "LOADTEST_REGISTRATION_SUBMIT_PATH": endpoints.registration_submit,
        "LOADTEST_LOGIN_SUBMIT_PATH": endpoints.login_submit,
        "LOADTEST_LESSON_PATH": endpoints.lesson,
        "LOADTEST_PROGRESS_PATH": endpoints.progress,
        "LOADTEST_CHECKOUT_PATH": endpoints.checkout,
        "LOADTEST_PAYMENT_STATUS_PATH": endpoints.payment_status,
    }
    return [name for name, value in required.items() if not value]
